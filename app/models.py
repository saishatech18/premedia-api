from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.db import Base

# 1. ROLES TABLE (For RBAC)
class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False) # e.g., "admin", "designer", "client"
    description = Column(String, nullable=True)

    # Link back to the users who have this role
    users = relationship("User", back_populates="role")


# 2. USERS TABLE
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False) # Never store plain text passwords!
    full_name = Column(String, nullable=True)
    
    # Foreign Key: This links the user directly to a specific role ID
    role_id = Column(Integer, ForeignKey("roles.id"))
    
    # Relationships
    role = relationship("Role", back_populates="users")
    artworks = relationship("Artwork", back_populates="owner")


# 3. ARTWORK STATUS (For the approval workflow)
class ArtworkStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# 4. ARTWORKS TABLE (DAM Metadata)
class Artwork(Base):
    __tablename__ = "artworks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    
    # This is the golden rule: We store the URL to the massive S3 file, NOT the file itself!
    file_url = Column(String, nullable=False) 
    file_size_mb = Column(Integer, nullable=True)
    status = Column(Enum(ArtworkStatus), default=ArtworkStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Foreign Key: Links the artwork to the user who uploaded it
    owner_id = Column(Integer, ForeignKey("users.id"))
    
    # Relationship
    owner = relationship("User", back_populates="artworks")