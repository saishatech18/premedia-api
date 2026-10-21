import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load variables from your .env file
load_dotenv()

# Get the Supabase connection string from .env
DATABASE_URL = os.getenv("DATABASE_URL")

# Establish the core connection to Supabase
engine = create_engine(DATABASE_URL)

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