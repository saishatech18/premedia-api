from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import re
from typing import List

from fastapi import APIRouter, FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import auth, models, schemas
from .db import SessionLocal, engine, get_db

models.Base.metadata.create_all(bind=engine)

IST = timezone(timedelta(hours=5, minutes=30))

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


class BulkJobAllocate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    job_ids: List[int] = Field(..., alias="jobIds")
    owner_id: int | None = Field(default=None, alias="ownerId")
    assigned_to: str = Field(..., alias="assignedTo")
    priority: str | None = None
    allocation_notes: str = Field(default="", alias="allocationNotes")


def _get_role_slug(user: models.User) -> str:
    if not user or not getattr(user, "role", None):
        return ""
    return (user.role.name or "").strip().lower()


def require_roles(*allowed_roles: str):
    allowed = {r.strip().lower() for r in allowed_roles}

    def _checker(current_user: models.User = Depends(auth.get_current_user)) -> models.User:
        role_slug = _get_role_slug(current_user)
        if role_slug not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role_slug or 'unknown'}' is not authorized for this action",
            )
        return current_user

    return _checker


def ensure_artwork_time_columns():
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE artworks ADD COLUMN IF NOT EXISTS actual_hours DOUBLE PRECISION DEFAULT 0.0")
        )
        conn.execute(
            text("ALTER TABLE artworks ADD COLUMN IF NOT EXISTS work_started_at TIMESTAMP NULL")
        )
        conn.execute(
            text("ALTER TABLE artworks ADD COLUMN IF NOT EXISTS operator_time_logs JSONB DEFAULT '{}'::jsonb")
        )
        conn.execute(
            text("ALTER TABLE artworks ADD COLUMN IF NOT EXISTS version_history JSONB DEFAULT '[]'::jsonb")
        )


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
    ensure_artwork_time_columns()
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


def _slugify(text_val: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "_", text_val.strip().lower()).strip("_")
    return clean or "tier"


def _parse_status(raw: str) -> models.ArtworkStatus:
    val = (raw or "new").strip()
    for member in models.ArtworkStatus:
        if member.value == val or member.value.lower() == val.lower():
            return member
    return models.ArtworkStatus.NEW


def _compute_shift_hours(start_utc: datetime, end_utc: datetime) -> float:
    """
    Calculates working hours in IST studio shift (09:30 - 18:30 Mon-Sat),
    automatically excluding 13:00 - 14:00 lunch break, overnight hours, and Sundays.
    """
    if not start_utc or not end_utc or end_utc <= start_utc:
        return 0.0

    start_ist = start_utc.replace(tzinfo=timezone.utc).astimezone(IST)
    end_ist = end_utc.replace(tzinfo=timezone.utc).astimezone(IST)

    total_seconds = 0.0
    cursor_day = start_ist.date()
    last_day = end_ist.date()

    while cursor_day <= last_day:
        if cursor_day.weekday() != 6:  # Exclude Sunday (6)
            morning_start = datetime(cursor_day.year, cursor_day.month, cursor_day.day, 9, 30, tzinfo=IST)
            morning_end = datetime(cursor_day.year, cursor_day.month, cursor_day.day, 13, 0, tzinfo=IST)
            afternoon_start = datetime(cursor_day.year, cursor_day.month, cursor_day.day, 14, 0, tzinfo=IST)
            afternoon_end = datetime(cursor_day.year, cursor_day.month, cursor_day.day, 18, 30, tzinfo=IST)

            for seg_start, seg_end in ((morning_start, morning_end), (afternoon_start, afternoon_end)):
                overlap_start = max(start_ist, seg_start)
                overlap_end = min(end_ist, seg_end)
                if overlap_end > overlap_start:
                    total_seconds += (overlap_end - overlap_start).total_seconds()

        cursor_day += timedelta(days=1)

    return round(total_seconds / 3600.0, 2)


def _credit_operator_hours(job: models.Artwork, session_hours: float, actor_key: str = ""):
    if session_hours <= 0:
        return
    logs = dict(job.operator_time_logs or {})
    key = (actor_key or "").strip()
    if not key:
        raw_assigned = (job.assigned_to or "").strip()
        if raw_assigned and raw_assigned.lower() != "unassigned":
            key = raw_assigned.split(",")[0].strip()
    if key:
        logs[key] = round(float(logs.get(key, 0.0)) + session_hours, 2)
        job.operator_time_logs = logs


def _get_version_history(job: models.Artwork) -> list:
    raw = getattr(job, "version_history", None)
    if isinstance(raw, list) and len(raw) > 0:
        return list(raw)
    if job.file_url:
        return [
            {
                "version": 1,
                "label": "v1",
                "fileUrl": job.file_url,
                "notes": job.notes or "Initial submission",
                "submittedBy": job.assigned_to or "Studio",
                "status": job.status.value if hasattr(job.status, "value") else str(job.status),
                "feedback": "",
                "timestamp": (job.created_at.isoformat() + "Z") if getattr(job, "created_at", None) else datetime.utcnow().isoformat() + "Z",
            }
        ]
    return []


def _record_version_submission(job: models.Artwork, file_url: str, notes: str, actor: str, now_utc: datetime):
    history = _get_version_history(job)
    # If v1 was just the initial brief asset and hasn't had a studio QC pass yet, update v1; otherwise append v2, v3...
    if len(history) == 1 and history[0].get("stage") == "ingest" and not history[0].get("feedback"):
        history[0]["fileUrl"] = file_url or history[0].get("fileUrl", "")
        history[0]["notes"] = notes or history[0].get("notes", "")
        history[0]["submittedBy"] = actor or job.assigned_to or "Studio"
        history[0]["stage"] = "qc_submitted"
        history[0]["timestamp"] = now_utc.isoformat() + "Z"
    else:
        next_ver = len(history) + 1
        history.append(
            {
                "version": next_ver,
                "label": f"v{next_ver}",
                "fileUrl": file_url or job.file_url or "",
                "notes": notes or f"Revision v{next_ver} submitted for QC",
                "submittedBy": actor or job.assigned_to or "Studio",
                "stage": "qc_submitted",
                "feedback": "",
                "timestamp": now_utc.isoformat() + "Z",
            }
        )
    job.version_history = history


def _attach_version_feedback(job: models.Artwork, feedback_text: str, decision: str, actor: str, now_utc: datetime):
    history = _get_version_history(job)
    if not history:
        return
    latest = dict(history[-1])
    latest["feedback"] = feedback_text or latest.get("feedback", "")
    latest["decision"] = decision
    latest["reviewedBy"] = actor
    latest["reviewedAt"] = now_utc.isoformat() + "Z"
    history[-1] = latest
    job.version_history = history


def _serialize_job(job: models.Artwork) -> dict:
    data = schemas.JobResponse.model_validate(job).model_dump()
    now_utc = datetime.utcnow()
    live_session_hours = (
        _compute_shift_hours(job.work_started_at, now_utc)
        if job.work_started_at and job.status in (models.ArtworkStatus.ACTIVE, models.ArtworkStatus.REWORK)
        else 0.0
    )
    banked_hours = float(job.actual_hours or 0.0)
    versions = _get_version_history(job)

    data["assignedTo"] = job.assigned_to or "Unassigned"
    data["fileUrl"] = job.file_url or ""
    data["projectCode"] = job.project_code or ""
    data["projectName"] = job.project_name or ""
    data["clientName"] = job.client_name or ""
    data["complexityTier"] = job.complexity_tier or "standard"
    data["estimatedHours"] = job.estimated_hours or 2.0
    data["actualHours"] = banked_hours
    data["liveSessionHours"] = live_session_hours
    data["effectiveActualHours"] = round(banked_hours + live_session_hours, 2)
    data["workStartedAt"] = job.work_started_at.isoformat() + "Z" if job.work_started_at else None
    data["operatorTimeLogs"] = job.operator_time_logs or {}
    data["versionHistory"] = versions
    data["currentVersion"] = len(versions) if versions else 1
    data["billableAmount"] = job.billable_amount or 0.0
    data["billingStatus"] = job.billing_status or "unbilled"
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
    dependencies=[Depends(require_roles("admin", "project_manager"))],
)
def create_job(job: schemas.JobCreate, db: Session = Depends(get_db)):
    due_naive = job.sla_due_date.replace(tzinfo=None) if job.sla_due_date else None
    parsed_status = _parse_status(job.status)
    now_utc = datetime.utcnow()
    initial_versions = []
    if job.file_url:
        initial_versions.append(
            {
                "version": 1,
                "label": "v1",
                "fileUrl": job.file_url,
                "notes": job.notes or "Initial brief & artwork ingested",
                "submittedBy": job.assigned_to or "Intake",
                "stage": "ingest",
                "feedback": "",
                "timestamp": now_utc.isoformat() + "Z",
            }
        )

    new_job = models.Artwork(
        title=job.title,
        file_url=job.file_url or "",
        file_size_mb=job.file_size_mb,
        status=parsed_status,
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
        actual_hours=0.0,
        work_started_at=now_utc if parsed_status == models.ArtworkStatus.ACTIVE else None,
        operator_time_logs={},
        version_history=initial_versions,
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


@api.patch(
    "/jobs/bulk-allocate",
    dependencies=[Depends(require_roles("admin", "project_manager"))],
)
def bulk_allocate_jobs(payload: BulkJobAllocate, db: Session = Depends(get_db)):
    if not payload.job_ids:
        return []

    jobs = db.query(models.Artwork).filter(models.Artwork.id.in_(payload.job_ids)).all()
    now_utc = datetime.utcnow()
    is_unallocating = (payload.assigned_to or "").strip().lower() in ("", "unassigned", "none")

    for job in jobs:
        if job.work_started_at and job.status in (models.ArtworkStatus.ACTIVE, models.ArtworkStatus.REWORK):
            elapsed = _compute_shift_hours(job.work_started_at, now_utc)
            job.actual_hours = round(float(job.actual_hours or 0.0) + elapsed, 2)
            _credit_operator_hours(job, elapsed)
            job.work_started_at = None

        if "owner_id" in payload.model_fields_set:
            job.owner_id = payload.owner_id
        job.assigned_to = payload.assigned_to
        if payload.priority:
            job.priority = payload.priority
        if payload.allocation_notes is not None:
            job.allocation_notes = payload.allocation_notes

        if is_unallocating:
            job.status = models.ArtworkStatus.NEW
            job.work_started_at = None
        elif job.status == models.ArtworkStatus.NEW:
            job.work_started_at = None

    db.commit()
    for job in jobs:
        db.refresh(job)
    return [_serialize_job(j) for j in jobs]


@api.patch(
    "/jobs/{job_id}/allocate",
    dependencies=[Depends(require_roles("admin", "project_manager"))],
)
def allocate_job(job_id: int, payload: schemas.JobAllocate, db: Session = Depends(get_db)):
    job = db.query(models.Artwork).filter(models.Artwork.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    now_utc = datetime.utcnow()
    is_unallocating = (payload.assigned_to or "").strip().lower() in ("", "unassigned", "none")

    if job.work_started_at and job.status in (models.ArtworkStatus.ACTIVE, models.ArtworkStatus.REWORK):
        elapsed = _compute_shift_hours(job.work_started_at, now_utc)
        job.actual_hours = round(float(job.actual_hours or 0.0) + elapsed, 2)
        _credit_operator_hours(job, elapsed)
        job.work_started_at = None

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

    if is_unallocating:
        job.status = models.ArtworkStatus.NEW
        job.work_started_at = None
    elif job.status == models.ArtworkStatus.NEW:
        job.work_started_at = None

    db.commit()
    db.refresh(job)
    return _serialize_job(job)


@api.patch("/jobs/{job_id}/command")
def command_job(
    job_id: int,
    cmd: schemas.JobCommand,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    job = db.query(models.Artwork).filter(models.Artwork.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    role_slug = _get_role_slug(current_user)
    now_utc = datetime.utcnow()
    data = cmd.payload or {}
    actor_email = data.get("logged_by") or data.get("loggedBy") or current_user.email or ""
    actor_name = current_user.full_name or actor_email or "Studio"

    # Server-side RBAC boundary checks
    if role_slug == "client":
        if cmd.commandName == "UPDATE_BILLING" or "billingStatus" in data or "billing_status" in data:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Clients cannot modify billing status")
        if "status" in data and data["status"]:
            requested = _parse_status(data["status"])
            if requested not in (models.ArtworkStatus.APPROVED, models.ArtworkStatus.REWORK):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Client reviewers can only approve or request revisions on proofs",
                )

    if ("billingStatus" in data or "billing_status" in data or cmd.commandName == "UPDATE_BILLING") and role_slug not in (
        "admin",
        "project_manager",
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and project managers can update billing status",
        )

    # 1. Handle direct session / handoff hours logging
    if "session_hours" in data or "sessionHours" in data:
        raw_session = data.get("session_hours") if "session_hours" in data else data.get("sessionHours")
        session_hrs = max(0.0, float(raw_session or 0.0))
        job.actual_hours = round(float(job.actual_hours or 0.0) + session_hrs, 2)
        _credit_operator_hours(job, session_hrs, actor_email)
        job.work_started_at = now_utc if job.status in (models.ArtworkStatus.ACTIVE, models.ArtworkStatus.REWORK) else None
    elif "actual_hours" in data or "actualHours" in data:
        raw_total = data.get("actual_hours") if "actual_hours" in data else data.get("actualHours")
        new_total = max(0.0, float(raw_total or 0.0))
        delta = round(new_total - float(job.actual_hours or 0.0), 2)
        job.actual_hours = new_total
        if delta > 0:
            _credit_operator_hours(job, delta, actor_email)
        job.work_started_at = None

    incoming_file_url = data.get("file_url") or data.get("fileUrl") or ""
    incoming_notes = data.get("notes") if "notes" in data else None

    # 2. Handle status transition & zero-button shift timer lifecycle
    if "status" in data and data["status"]:
        next_status = _parse_status(data["status"])

        if (
            next_status in (models.ArtworkStatus.QC, models.ArtworkStatus.REVIEW, models.ArtworkStatus.APPROVED)
            and job.work_started_at
            and "session_hours" not in data
            and "sessionHours" not in data
            and "actual_hours" not in data
            and "actualHours" not in data
        ):
            auto_elapsed = _compute_shift_hours(job.work_started_at, now_utc)
            job.actual_hours = round(float(job.actual_hours or 0.0) + auto_elapsed, 2)
            _credit_operator_hours(job, auto_elapsed, actor_email)
            job.work_started_at = None

        if next_status in (models.ArtworkStatus.ACTIVE, models.ArtworkStatus.REWORK):
            if not job.work_started_at:
                job.work_started_at = now_utc
        elif next_status in (models.ArtworkStatus.QC, models.ArtworkStatus.REVIEW, models.ArtworkStatus.APPROVED, models.ArtworkStatus.NEW):
            job.work_started_at = None

        # Record version snapshot on QC submission
        if next_status == models.ArtworkStatus.QC or cmd.commandName == "SUBMIT_QC":
            _record_version_submission(
                job,
                incoming_file_url or job.file_url or "",
                incoming_notes or job.notes or "",
                actor_name,
                now_utc,
            )

        # Record review feedback on rejection / approval
        if cmd.commandName in ("CLIENT_REJECT", "QC_REJECT") or (
            next_status == models.ArtworkStatus.REWORK and incoming_notes
        ):
            _attach_version_feedback(
                job,
                incoming_notes or "Revision requested",
                "changes_requested",
                actor_name,
                now_utc,
            )
        elif next_status == models.ArtworkStatus.APPROVED or cmd.commandName == "CLIENT_APPROVE":
            _attach_version_feedback(
                job,
                incoming_notes or "Approved for commercial release",
                "approved",
                actor_name,
                now_utc,
            )

        job.status = next_status
        if next_status == models.ArtworkStatus.APPROVED and (job.billing_status or "unbilled") == "unbilled":
            job.billing_status = "ready_to_invoice"

    # 3. Handle billing status updates (unbilled / ready_to_invoice / invoiced / paid)
    raw_billing = data.get("billing_status") or data.get("billingStatus")
    if raw_billing:
        clean_billing = str(raw_billing).strip().lower()
        if clean_billing in ("unbilled", "ready_to_invoice", "invoiced", "paid"):
            job.billing_status = clean_billing

    if incoming_file_url:
        job.file_url = incoming_file_url
    if incoming_notes is not None:
        job.notes = incoming_notes
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