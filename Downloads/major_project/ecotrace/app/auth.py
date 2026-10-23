"""JWT authentication helpers.

Roles:
  admin   — can create facilities, producers, pickers; approve HITL; revoke badges.
  operator — can create collections, submit evidence/completion/narration.
  viewer  — read-only (GET endpoints, marketplace).

SECRET_KEY / ACCESS_TOKEN_EXPIRE_MINUTES are read from environment variables with
safe defaults so the app starts in dev without any configuration.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY: str = os.getenv("SECRET_KEY", "ecotrace-dev-secret-change-in-prod-32chars!!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# ── Crypto ────────────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Tokens ────────────────────────────────────────────────────────────────────
def create_access_token(subject: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_or_expired_token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Dependencies ──────────────────────────────────────────────────────────────
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = _decode_token(token)
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid_token_subject")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="user_not_found_or_inactive")
    return user


def require_role(*roles: str):
    """Factory: returns a dependency that enforces one of the given roles."""
    def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires_role:{','.join(roles)}",
            )
        return current_user
    return _check


# Convenience role deps
require_admin    = require_role("admin")
require_operator = require_role("admin", "operator")
require_viewer   = require_role("admin", "operator", "viewer")
