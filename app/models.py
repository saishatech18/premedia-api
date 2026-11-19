from sqlalchemy import Boolean, Column, Integer, Float, String, ForeignKey, DateTime, Enum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.db import Base


# 1. ROLES TABLE (For RBAC)
class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)

    users = relationship("User", back_populates="role")


# 2. USERS TABLE
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)

    role_id = Column(Integer, ForeignKey("roles.id"))

    role = relationship("Role", back_populates="users")
    artworks = relationship("Artwork", back_populates="owner")


# 3. COMPLEXITY TIERS TABLE (Admin-configurable timelines, hours & rates)
class ComplexityTier(Base):
    __tablename__ = "complexity_tiers"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    label = Column(String, nullable=False)
    sla_hours = Column(Integer, default=24, nullable=False)
    est_hours = Column(Float, default=2.0, nullable=False)
    rate = Column(Float, default=2500.0, nullable=False)
    color = Column(String, default="emerald", nullable=False)
    is_custom = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)


# 4. ARTWORK STATUS (Matches Postgres artworkstatus enum values)
class ArtworkStatus(enum.Enum):
    NEW = "new"
    ACTIVE = "active"
    REWORK = "rework"
    QC = "qc"
    REVIEW = "review"
    APPROVED = "approved"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


# 5. ARTWORKS TABLE (Complete Premedia Hub Pipeline, DAM & Time Tracking Metadata)
class Artwork(Base):
    __tablename__ = "artworks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    file_url = Column(String, nullable=False, default="")
    file_size_mb = Column(Integer, nullable=True)
    status = Column(
        Enum(
            ArtworkStatus,
            values_callable=lambda obj: [e.value for e in obj],
            name="artworkstatus",
        ),
        default=ArtworkStatus.NEW,
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Assignment & Notes
    assigned_to = Column(String, default="Unassigned", nullable=True)
    notes = Column(String, default="", nullable=True)
    allocation_notes = Column(String, default="", nullable=True)

    # Project / Campaign Grouping
    project_code = Column(String, index=True, default="", nullable=True)
    project_name = Column(String, default="", nullable=True)

    # Client & SKU Identification
    client_name = Column(String, index=True, default="", nullable=True)
    brand_name = Column(String, default="", nullable=True)
    sku_code = Column(String, default="", nullable=True)

    # Complexity Tier, Commercial Billing & Actual Effort Tracking
    complexity_tier = Column(String, default="standard", nullable=True)
    sla_hours = Column(Integer, default=24, nullable=True)
    estimated_hours = Column(Float, default=2.0, nullable=True)
    actual_hours = Column(Float, default=0.0, nullable=True)
    work_started_at = Column(DateTime, nullable=True)
    operator_time_logs = Column(JSON, default=dict, nullable=True)
    version_history = Column(JSON, default=list, nullable=True)
    pins = Column(JSON, default=list, nullable=True)
    billing_currency = Column(String, default="INR", nullable=True)
    billable_amount = Column(Float, default=2500.0, nullable=True)
    billing_status = Column(String, default="unbilled", nullable=True)

    # Technical Press & Preflight Specs
    print_process = Column(String, default="Offset Litho", nullable=True)
    color_profile = Column(String, default="CMYK + Spot (Pantone)", nullable=True)
    trim_size = Column(String, default="", nullable=True)
    bleed_mm = Column(Float, default=3.0, nullable=True)
    priority = Column(String, default="normal", nullable=True)
    sla_due_date = Column(DateTime, nullable=True)
    preflight_status = Column(String, default="passed", nullable=True)
    preflight_checks = Column(JSON, default=dict, nullable=True)
    skill_required = Column(String, default="Packaging / Dieline", nullable=True)

    owner = relationship("User", back_populates="artworks")