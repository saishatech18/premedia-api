from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

# Establish the core connection to Supabase
engine = create_engine(settings.database_url, pool_pre_ping=True)

# Create a session factory to handle individual database transactions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# This Base class is inherited by your database models (Users, Roles, Artworks)
Base = declarative_base()

# A helper function to safely open and close database sessions for your API routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
