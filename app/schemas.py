from pydantic import BaseModel, BeforeValidator, EmailStr, Field
from typing import Annotated, Optional


def _normalize_email(value):
    return value.strip().lower() if isinstance(value, str) else value


# Emails are stored and looked up trimmed and lowercased
NormalizedEmail = Annotated[EmailStr, BeforeValidator(_normalize_email)]
LoginEmail = Annotated[str, BeforeValidator(_normalize_email)]

# The upper bound also limits hashing work on the public login endpoint
PASSWORD_MAX_LENGTH = 128


# Schema for role output
class RoleResponse(BaseModel):
    id: int
    name: str  # stable slug, e.g. "operator_retouching"
    description: Optional[str] = None  # display label, e.g. "Operator (Retouching)"

    class Config:
        from_attributes = True


# Schema for creating a user
class UserCreate(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=8, max_length=PASSWORD_MAX_LENGTH)
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
    email: LoginEmail
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


# Schema for a successful login
class LoginResponse(BaseModel):
    token: str
    user: UserResponse
