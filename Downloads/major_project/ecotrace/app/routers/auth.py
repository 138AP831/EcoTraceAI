"""Authentication endpoints: register and login."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

_VALID_ROLES = {"admin", "operator", "viewer"}


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None
    role: str = "viewer"

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        if v not in _VALID_ROLES:
            raise ValueError(f"role must be one of {_VALID_ROLES}")
        return v

    @field_validator("password")
    @classmethod
    def _check_pw(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    full_name: str | None
    is_active: bool

    model_config = {"from_attributes": True}


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="email_already_registered")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        full_name=payload.full_name,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="account_inactive")
    token = create_access_token(subject=user.id, role=user.role)
    return TokenResponse(access_token=token, role=user.role, user_id=user.id)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    """Returns the currently authenticated user's profile."""
    return current_user
