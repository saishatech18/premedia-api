from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from . import models, schemas
from .db import engine, get_db

# Create database tables if they do not exist
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Premedia Hub API")

# Enable CORS for local frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Schema for login requests
class LoginRequest(BaseModel):
    email: str
    password: str


@app.on_event("startup")
def startup_event():
    # Seed default RBAC roles if they are missing
    db: Session = next(get_db())
    try:
        default_roles = ["Admin", "Production", "Quality", "Client"]
        for role_name in default_roles:
            existing = (
                db.query(models.Role).filter(models.Role.name == role_name).first()
            )
            if not existing:
                db.add(models.Role(name=role_name))
        db.commit()
    finally:
        db.close()


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Premedia Hub API is running"}


@app.get("/users/", response_model=List[schemas.UserResponse])
def get_users(db: Session = Depends(get_db)):
    """Fetch all users along with their assigned role."""
    users = db.query(models.User).all()
    return users


@app.post(
    "/users/",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
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
        db.query(models.Role).filter(models.Role.name == user.role).first()
    )
    if not role_obj:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{user.role}' not recognized",
        )

    new_user = models.User(
        email=user.email,
        hashed_password=user.password,
        role_id=role_obj.id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@app.post("/login/")
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """Verify user email and password."""
    user = (
        db.query(models.User)
        .filter(models.User.email == credentials.email)
        .first()
    )

    if not user or user.hashed_password != credentials.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return {
        "message": "Login successful",
        "user": {
            "id": user.id,
            "email": user.email,
            "role_id": user.role_id,
        },
    }