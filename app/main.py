from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db import engine, SessionLocal, Base, get_db
from app import models

DEFAULT_ROLES = [
    {"name": "admin", "description": "Full access to settings, user management, and assets"},
    {"name": "designer", "description": "Can upload, edit, and manage design assets"},
    {"name": "client", "description": "Read-only access and artwork approval rights"},
]

def seed_roles():
    db = SessionLocal()
    try:
        # Check if roles are already populated
        existing_count = db.query(models.Role).count()
        if existing_count == 0:
            for role_data in DEFAULT_ROLES:
                role = models.Role(**role_data)
                db.add(role)
            db.commit()
            print("Default RBAC roles seeded successfully.")
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables if they do not exist
    Base.metadata.create_all(bind=engine)
    # Seed default roles
    seed_roles()
    yield

# Initialize the FastAPI app
app = FastAPI(lifespan=lifespan, title="Premedia API")

# --- CORS SETUP ---
# This MUST be placed right after the app is created to allow frontend connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, change this to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allows all headers
)
# ------------------

# --- Pydantic Schemas for Data Validation ---
class UserCreate(BaseModel):
    email: str
    password: str
    role_id: int = 3  # Defaults to 3 (client)

class UserResponse(BaseModel):
    id: int
    email: str
    role_id: int

    class Config:
        from_attributes = True

# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"status": "success", "message": "Premedia API running and database initialized"}

@app.post("/users/", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    # Check if the email is already in the database
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create the user mapping fields to the database columns
    new_user = models.User(
        email=user.email, 
        hashed_password=user.password, 
        role_id=user.role_id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user