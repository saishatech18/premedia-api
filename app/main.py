from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db import engine, SessionLocal, Base
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

app = FastAPI(lifespan=lifespan, title="Premedia API")

@app.get("/")
def read_root():
    return {"status": "success", "message": "Premedia API running and database initialized"}