from datetime import datetime
from typing import Annotated, Dict, Optional
from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field


def _normalize_email(value):
    return value.strip().lower() if isinstance(value, str) else value


NormalizedEmail = Annotated[EmailStr, BeforeValidator(_normalize_email)]
LoginEmail = Annotated[str, BeforeValidator(_normalize_email)]

PASSWORD_MAX_LENGTH = 128


# =====================================================================
# 1. AUTH, ROLE & USER SCHEMAS
# =====================================================================

class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=8, max_length=PASSWORD_MAX_LENGTH)
    role: str
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role_id: Optional[int] = None
    role: Optional[RoleResponse] = None

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: LoginEmail
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class LoginResponse(BaseModel):
    token: str
    user: UserResponse


# =====================================================================
# 2. COMPLEXITY TIERS SCHEMAS (Studio Default & Client-Specific Rate Cards)
# =====================================================================

class ComplexityTierCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    client_name: Optional[str] = Field(default=None, alias="clientName")
    slug: Optional[str] = None
    label: str
    sla_hours: int = Field(default=24, alias="slaHours")
    est_hours: float = Field(default=2.0, alias="estHours")
    rate: float = 0.0
    currency: str = "INR"
    color: str = "emerald"
    is_custom: bool = Field(default=False, alias="isCustom")
    sort_order: int = Field(default=0, alias="sortOrder")


class ComplexityTierUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    client_name: Optional[str] = Field(default=None, alias="clientName")
    label: Optional[str] = None
    sla_hours: Optional[int] = Field(default=None, alias="slaHours")
    est_hours: Optional[float] = Field(default=None, alias="estHours")
    rate: Optional[float] = None
    currency: Optional[str] = None
    color: Optional[str] = None
    is_custom: Optional[bool] = Field(default=None, alias="isCustom")
    sort_order: Optional[int] = Field(default=None, alias="sortOrder")


class ComplexityTierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    client_name: Optional[str] = None
    slug: str
    label: str
    sla_hours: int
    est_hours: float
    rate: float
    currency: str = "INR"
    color: str
    is_custom: bool
    sort_order: int


# =====================================================================
# 3. PREMEDIA JOB / ARTWORK SCHEMAS (Aligned with public.artworks)
# =====================================================================

class JobCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    title: str
    file_url: str = Field(default="", alias="fileUrl")
    file_size_mb: Optional[int] = Field(default=None, alias="fileSizeMb")
    status: str = "new"
    owner_id: Optional[int] = Field(default=None, alias="ownerId")
    assigned_to: str = Field(default="Unassigned", alias="assignedTo")
    notes: str = ""

    project_code: str = Field(default="", alias="projectCode")
    project_name: str = Field(default="", alias="projectName")

    client_name: str = Field(default="", alias="clientName")
    brand_name: str = Field(default="", alias="brandName")
    sku_code: str = Field(default="", alias="skuCode")

    complexity_tier: str = Field(default="standard", alias="complexityTier")
    sla_hours: int = Field(default=24, alias="slaHours")
    estimated_hours: float = Field(default=2.0, alias="estimatedHours")
    billing_currency: str = Field(default="INR", alias="billingCurrency")
    billable_amount: float = Field(default=2500.0, alias="billableAmount")
    billing_status: str = Field(default="unbilled", alias="billingStatus")

    print_process: str = Field(default="Offset Litho", alias="printProcess")
    color_profile: str = Field(default="CMYK + Spot (Pantone)", alias="colorProfile")
    trim_size: str = Field(default="", alias="trimSize")
    bleed_mm: float = Field(default=3.0, alias="bleedMm")
    priority: str = "normal"
    sla_due_date: Optional[datetime] = Field(default=None, alias="slaDueDate")
    preflight_status: str = Field(default="passed", alias="preflightStatus")
    preflight_checks: Dict[str, bool] = Field(default_factory=dict, alias="preflightChecks")
    skill_required: str = Field(default="Packaging / Dieline", alias="skillRequired")


class JobAllocate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    owner_id: Optional[int] = Field(default=None, alias="ownerId")
    assigned_to: str = Field(..., alias="assignedTo")
    complexity_tier: Optional[str] = Field(default=None, alias="complexityTier")
    estimated_hours: float = Field(default=2.0, alias="estimatedHours")
    billable_amount: Optional[float] = Field(default=None, alias="billableAmount")
    priority: Optional[str] = None
    allocation_notes: str = Field(default="", alias="allocationNotes")
    status: str = "active"


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    title: str
    file_url: Optional[str] = ""
    file_size_mb: Optional[int] = None
    status: str
    created_at: Optional[datetime] = None
    owner_id: Optional[int] = None
    assigned_to: Optional[str] = "Unassigned"
    notes: Optional[str] = ""

    project_code: Optional[str] = ""
    project_name: Optional[str] = ""

    client_name: Optional[str] = ""
    brand_name: Optional[str] = ""
    sku_code: Optional[str] = ""

    complexity_tier: Optional[str] = "standard"
    sla_hours: Optional[int] = 24
    estimated_hours: Optional[float] = 2.0
    actual_hours: Optional[float] = 0.0
    work_started_at: Optional[datetime] = None
    operator_time_logs: Optional[Dict[str, float]] = Field(default_factory=dict)
    billing_currency: Optional[str] = "INR"
    billable_amount: Optional[float] = 2500.0
    billing_status: Optional[str] = "unbilled"

    print_process: Optional[str] = "Offset Litho"
    color_profile: Optional[str] = "CMYK + Spot (Pantone)"
    trim_size: Optional[str] = ""
    bleed_mm: Optional[float] = 3.0
    priority: Optional[str] = "normal"
    sla_due_date: Optional[datetime] = None
    preflight_status: Optional[str] = "pending"
    preflight_checks: Optional[Dict[str, bool]] = Field(default_factory=dict)
    skill_required: Optional[str] = "Packaging / Dieline"
    allocation_notes: Optional[str] = ""


class JobCommand(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    commandName: str
    payload: Dict = Field(default_factory=dict)
    auditDetails: Optional[str] = None