from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List

from . import auth, models, schemas
from .db import SessionLocal, engine, get_db

# Create database tables if they do not exist
models.Base.metadata.create_all(bind=engine)

# Default RBAC roles: slug -> display label (stored in Role.description)
DEFAULT_ROLES = {
    "admin": "Administrator",
    "project_manager": "Project Manager",
    "operator_retouching": "Operator (Retouching)",
    "operator_cgi": "Operator (CGI/DTP)",
    "qc": "QC / Pre-flight",
    "client": "Client (External Reviewer)",
}


def seed_roles():
    # Seed default RBAC roles if they are missing, and keep their labels current
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_roles()
    yield


app = FastAPI(title="Premedia Hub API", lifespan=lifespan)

# Auth uses Bearer tokens, not cookies, so CORS doesn't need credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All API endpoints live under /api (no trailing slashes)
api = APIRouter(prefix="/api")


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Premedia Hub API is running"}


@api.get(
    "/users",
    response_model=List[schemas.UserResponse],
    dependencies=[Depends(auth.get_current_user)],
)
def get_users(db: Session = Depends(get_db)):
    """Fetch all users along with their assigned role."""
    users = db.query(models.User).all()
    return users


@api.post(
    "/users",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_admin_or_first_user)],
)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = (
        db.query(models.User).filter(models.User.email == user.email).first()
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Validate that the role exists
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
        # A concurrent request created the same email after the check above
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    db.refresh(new_user)

    return new_user


@api.post("/auth/login", response_model=schemas.LoginResponse)
def login(credentials: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Verify user email and password and issue an access token."""
    user = auth.authenticate_user(db, credentials.email, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return {"token": auth.create_access_token(user), "user": user}


app.include_router(api)
