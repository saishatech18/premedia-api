"""Password hashing, JWT access tokens, and auth dependencies for routes."""
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .db import get_db

password_hash = PasswordHash.recommended()  # Argon2

# Verified against when the email is unknown, so login takes the same time either way
DUMMY_HASH = password_hash.hash("dummy-password")

# auto_error=False so a missing token returns our 401 instead of FastAPI's default
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    """Return the user if the email and password match, otherwise None."""
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        password_hash.verify(password, DUMMY_HASH)
        return None
    if not password_hash.verify(password, user.hashed_password):
        return None
    return user


def create_access_token(user: models.User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": str(user.id), "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    """Return the user for the Bearer token, or None if no token was sent.

    An invalid or expired token, or one for a deleted user, is a 401.
    """
    if credentials is None:
        return None
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise _unauthorized()

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise _unauthorized()
    return user


def get_current_user(
    user: Optional[models.User] = Depends(get_optional_user),
) -> models.User:
    """Require a logged-in user."""
    if user is None:
        raise _unauthorized()
    return user


def require_admin_or_first_user(
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(get_optional_user),
) -> Optional[models.User]:
    """Require an admin, unless there are no users yet.

    The very first user is created without a token (via curl or /docs) and is
    expected to be the admin. Every user after that must be created by an admin.
    """
    if db.query(models.User).first() is None:
        return None
    if user is None:
        raise _unauthorized()
    if user.role is None or user.role.name != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an admin can create users",
        )
    return user
