from contextlib import asynccontextmanager
import re
from typing import List

from fastapi import APIRouter, FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import auth, models, schemas
from .db import SessionLocal, engine, get_db

models.Base.metadata.create_all(bind=engine)

DEFAULT_ROLES = {
    "admin": "Administrator",
    "project_manager": "Project Manager",
    "operator_retouching": "Operator (Retouching)",
    "operator_cgi": "Operator (CGI/DTP)",
    "qc": "QC / Pre-flight",
    "client": "Client (External Reviewer)",
}

DEFAULT_COMPLEXITY_TIERS = [
    {
        "slug": "standard",
        "label": "Standard",
        "sla_hours": 24,
        "est_hours": 2.0,
        "rate": 2500.0,
        "color": "emerald",
        "is_custom": False,
        "sort_order": 1,
    },
    {
        "slug": "medium",
        "label": "Medium",
        "sla_hours": 48,
        "est_hours": 4.5,
        "rate": 5500.0,
        "color": "blue",
        "is_custom": False,
        "sort_order": 2,
    },
    {
        "slug": "complex",
        "label": "Complex",
        "sla_hours": 72,
        "est_hours": 8.0,
        "rate": 10000.0,
        "color": "purple",
        "is_custom": False,
        "sort_order": 3,
    },
    {
        "slug": "custom",
        "label": "Custom",
        "sla_hours": 96,
        "est_hours": 12.0,
        "rate": 0.0,
        "color": "amber",
        "is_custom": True,
        "sort_order": 4,
    },
]


def seed_roles():
    with SessionLocal() as db:
        for role_name, label in DEFAULT_ROLES.items():
            existing = (
                db.query(models.Role)
                .filter(func.lower(models.Role.name) == role_name)
                .first()
            )
            if not existing:
                db.add(models.Role(name=role_name, description=label))
            elif existing.description != label:
                existing.description = label
        db.commit()


def seed_complexity_tiers():
    with SessionLocal() as db:
        existing_count = db.query(models.ComplexityTier).count()
        if existing_count == 0:
            for item in DEFAULT_COMPLEXITY_TIERS:
                db.add(models.ComplexityTier(**item))
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_roles()
    seed_complexity_tiers()
    yield


app = FastAPI(title="Premedia Hub API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


def _slugify(text: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return clean or "tier"


def _parse_status(raw: str) -> models.ArtworkStatus:
    val = (raw or "new").strip()
    for member in models.ArtworkStatus:
        if member.value == val or member.value.lower() == val.lower():
            return member
    return models.ArtworkStatus.NEW


def _serialize_job(job: models.Artwork) -> dict:
    data = schemas.JobResponse.model_validate(job).model_dump()
    data["assignedTo"] = job.assigned_to or "Unassigned"
    data["fileUrl"] = job.file_url or ""
    data["projectCode"] = job.project_code or ""
    data["projectName"] = job.project_name or ""
    data["clientName"] = job.client_name or ""
    data["complexityTier"] = job.complexity_tier or "standard"
    data["estimatedHours"] = job.estimated_hours or 2.0
    data["billableAmount"] = job.billable_amount or 0.0
    return data


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Premedia Hub API is running"}


@api.get(
    "/users",
    response_model=List[schemas.UserResponse],
    dependencies=[Depends(auth.get_current_user)],
)
def get_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()


@api.post(
    "/users",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_admin_or_first_user)],
)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = (
        db.query(models.User).filter(models.User.email == user.email).first()
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    role_obj = (
        db.query(models.Role)
        .filter(func.lower(models.Role.name) == user.role.lower())
        .first()
    )
    if not role_obj:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{user.role}' not recognized",
        )

    new_user = models.User(
        email=user.email,
        hashed_password=auth.hash_password(user.password),
        full_name=user.full_name,
        role_id=role_obj.id,
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    db.refresh(new_user)
    return new_user


@api.post("/auth/login", response_model=schemas.LoginResponse)
def login(credentials: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, credentials.email, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return {"token": auth.create_access_token(user), "user": user}


# =====================================================================
# COMPLEXITY TIERS ENDPOINTS (Database-driven Matrix)
# =====================================================================

@api.get(
    "/complexity-tiers",
    response_model=List[schemas.ComplexityTierResponse],
    dependencies=[Depends(auth.get_current_user)],
)
def get_complexity_tiers(db: Session = Depends(get_db)):
    return (
        db.query(models.ComplexityTier)
        .order_by(models.ComplexityTier.sort_order.asc(), models.ComplexityTier.id.asc())
        .all()
    )


@api.post(
    "/complexity-tiers",
    response_model=schemas.ComplexityTierResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_admin_or_first_user)],
)
def create_complexity_tier(payload: schemas.ComplexityTierCreate, db: Session = Depends(get_db)):
    base_slug = _slugify(payload.slug or payload.label)
    slug = base_slug
    counter = 2
    while db.query(models.ComplexityTier).filter(models.ComplexityTier.slug == slug).first():
        slug = f"{base_slug}_{counter}"
        counter += 1

    max_order = db.query(func.max(models.ComplexityTier.sort_order)).scalar() or 0
    tier = models.ComplexityTier(
        slug=slug,
        label=payload.label.strip(),
        sla_hours=max(1, int(payload.sla_hours)),
        est_hours=max(0.5, float(payload.est_hours)),
        rate=max(0.0, float(payload.rate)),
        color=payload.color or "emerald",
        is_custom=bool(payload.is_custom),
        sort_order=payload.sort_order if payload.sort_order > 0 else max_order + 1,
    )
    db.add(tier)
    db.commit()
    db.refresh(tier)
    return tier


@api.patch(
    "/complexity-tiers/{tier_id}",
    response_model=schemas.ComplexityTierResponse,
    dependencies=[Depends(auth.require_admin_or_first_user)],
)
def update_complexity_tier(
    tier_id: int, payload: schemas.ComplexityTierUpdate, db: Session = Depends(get_db)
):
    tier = db.query(models.ComplexityTier).filter(models.ComplexityTier.id == tier_id).first()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complexity tier not found")

    if payload.label is not None and payload.label.strip():
        tier.label = payload.label.strip()
    if payload.sla_hours is not None:
        tier.sla_hours = max(1, int(payload.sla_hours))
    if payload.est_hours is not None:
        tier.est_hours = max(0.5, float(payload.est_hours))
    if payload.rate is not None:
        tier.rate = max(0.0, float(payload.rate))
    if payload.color is not None:
        tier.color = payload.color
    if payload.is_custom is not None:
        tier.is_custom = payload.is_custom
    if payload.sort_order is not None:
        tier.sort_order = payload.sort_order

    db.commit()
    db.refresh(tier)
    return tier


@api.delete(
    "/complexity-tiers/{tier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(auth.require_admin_or_first_user)],
)
def delete_complexity_tier(tier_id: int, db: Session = Depends(get_db)):
    tier = db.query(models.ComplexityTier).filter(models.ComplexityTier.id == tier_id).first()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complexity tier not found")
    if db.query(models.ComplexityTier).count() <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one complexity tier must remain configured",
        )
    db.delete(tier)
    db.commit()
    return None


# =====================================================================
# PREMEDIA WORKFLOW / JOBS ENDPOINTS
# =====================================================================

@api.get("/jobs", dependencies=[Depends(auth.get_current_user)])
def get_jobs(db: Session = Depends(get_db)):
    jobs = db.query(models.Artwork).order_by(models.Artwork.id.desc()).all()
    return [_serialize_job(j) for j in jobs]


@api.post(
    "/jobs",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.get_current_user)],
)
def create_job(job: schemas.JobCreate, db: Session = Depends(get_db)):
    due_naive = job.sla_due_date.replace(tzinfo=None) if job.sla_due_date else None

    new_job = models.Artwork(
        title=job.title,
        file_url=job.file_url or "",
        file_size_mb=job.file_size_mb,
        status=_parse_status(job.status),
        owner_id=job.owner_id,
        assigned_to=job.assigned_to or "Unassigned",
        notes=job.notes or "",
        project_code=job.project_code or "",
        project_name=job.project_name or "",
        client_name=job.client_name or "",
        brand_name=job.brand_name or "",
        sku_code=job.sku_code or "",
        complexity_tier=job.complexity_tier or "standard",
        sla_hours=job.sla_hours,
        estimated_hours=job.estimated_hours,
        billing_currency=job.billing_currency or "INR",
        billable_amount=job.billable_amount,
        billing_status=job.billing_status or "unbilled",
        print_process=job.print_process or "Offset Litho",
        color_profile=job.color_profile or "CMYK + Spot (Pantone)",
        trim_size=job.trim_size or "",
        bleed_mm=job.bleed_mm,
        priority=job.priority or "normal",
        sla_due_date=due_naive,
        preflight_status=job.preflight_status or "passed",
        preflight_checks=job.preflight_checks or {},
        skill_required=job.skill_required or "Packaging / Dieline",
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return _serialize_job(new_job)


@api.patch("/jobs/{job_id}/allocate", dependencies=[Depends(auth.get_current_user)])
def allocate_job(job_id: int, payload: schemas.JobAllocate, db: Session = Depends(get_db)):
    job = db.query(models.Artwork).filter(models.Artwork.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if "owner_id" in payload.model_fields_set:
        job.owner_id = payload.owner_id
    job.assigned_to = payload.assigned_to
    if payload.complexity_tier:
        job.complexity_tier = payload.complexity_tier
    if payload.estimated_hours is not None:
        job.estimated_hours = payload.estimated_hours
    if payload.billable_amount is not None:
        job.billable_amount = payload.billable_amount
    if payload.priority:
        job.priority = payload.priority
    if payload.allocation_notes is not None:
        job.allocation_notes = payload.allocation_notes
    if payload.status:
        job.status = _parse_status(payload.status)

    db.commit()
    db.refresh(job)
    return _serialize_job(job)


@api.patch("/jobs/{job_id}/command", dependencies=[Depends(auth.get_current_user)])
def command_job(job_id: int, cmd: schemas.JobCommand, db: Session = Depends(get_db)):
    job = db.query(models.Artwork).filter(models.Artwork.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    data = cmd.payload or {}
    if "status" in data and data["status"]:
        job.status = _parse_status(data["status"])
        if str(data["status"]).lower() == "approved":
            job.billing_status = "ready_to_invoice"
    if "file_url" in data and data["file_url"]:
        job.file_url = data["file_url"]
    elif "fileUrl" in data and data["fileUrl"]:
        job.file_url = data["fileUrl"]
    if "notes" in data and data["notes"] is not None:
        job.notes = data["notes"]
    if "assigned_to" in data and data["assigned_to"]:
        job.assigned_to = data["assigned_to"]
    elif "assignedTo" in data and data["assignedTo"]:
        job.assigned_to = data["assignedTo"]
    if "priority" in data and data["priority"]:
        job.priority = data["priority"]

    db.commit()
    db.refresh(job)
    return _serialize_job(job)


app.include_router(api)