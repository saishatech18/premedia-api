from pydantic import BaseModel
from typing import Optional


# Schema for role output
class RoleResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


# Schema for creating a user
class UserCreate(BaseModel):
    email: str
    password: str
    role: str


# Schema for returning user data with role details
class UserResponse(BaseModel):
    id: int
    email: str
    role_id: Optional[int] = None
    role: Optional[RoleResponse] = None

    class Config:
        from_attributes = True


# Schema for login credentials
class LoginRequest(BaseModel):
    email: str
    password: str