from pydantic import BaseModel
from typing import Optional


# Schema for role output
class RoleResponse(BaseModel):
    id: int
    name: str  # stable slug, e.g. "operator_retouching"
    description: Optional[str] = None  # display label, e.g. "Operator (Retouching)"

    class Config:
        from_attributes = True


# Schema for creating a user
class UserCreate(BaseModel):
    email: str
    password: str
    role: str  # role slug
    full_name: Optional[str] = None


# Schema for returning user data with role details
class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role_id: Optional[int] = None
    role: Optional[RoleResponse] = None

    class Config:
        from_attributes = True


# Schema for login credentials
class LoginRequest(BaseModel):
    email: str
    password: str


# Schema for a successful login
class LoginResponse(BaseModel):
    token: str
    user: UserResponse
