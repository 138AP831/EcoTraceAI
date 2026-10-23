"""Shared pytest fixtures: fresh in-memory SQLite per test (StaticPool).

Auth layer (Step 2): each test gets a TestClient pre-seeded with an admin
user and a valid Bearer token, so all existing tests continue to pass without
modification.

Step 3 additions:
  - operator_client / viewer_client fixtures for access-control tests
  - Clock fixture for time-injection in behaviour tests
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  register models on Base
from app.auth import create_access_token, hash_password
from app.db import Base, get_db
from app.main import app
from app.models import User

_ADMIN_EMAIL    = "admin@test.local"
_ADMIN_PASSWORD = "adminpass1"
_ADMIN_ROLE     = "admin"

_OPERATOR_EMAIL    = "operator@test.local"
_OPERATOR_PASSWORD = "operatorpass1"
_OPERATOR_ROLE     = "operator"

_VIEWER_EMAIL    = "viewer@test.local"
_VIEWER_PASSWORD = "viewerpass1"
_VIEWER_ROLE     = "viewer"


# ── Clock ──────────────────────────────────────────────────────────────────────
class Clock:
    """Injectable time source for behaviour tests.

    The engine and services use datetime.utcnow() directly; this clock is
    used by tests to compute *input* timestamps relative to a controlled
    reference point (e.g. intake_at, submitted_at) without patching the
    stdlib. Pass clock.now() or clock.shift(hours=72) as intake_at /
    submitted_at values in test requests.
    """

    def __init__(self, start: datetime | None = None):
        self._base: datetime = start or datetime(2026, 6, 1, 0, 0, 0)

    def now(self) -> datetime:
        return self._base

    def shift(self, **kwargs) -> datetime:
        """Return a new datetime shifted by the given timedelta kwargs."""
        return self._base + timedelta(**kwargs)

    def advance(self, **kwargs) -> None:
        """Move the clock forward in place."""
        self._base += timedelta(**kwargs)

    def isoformat(self) -> str:
        return self._base.isoformat()


@pytest.fixture
def clock() -> Clock:
    """A fresh Clock anchored at 2026-06-01 00:00:00 UTC (naive)."""
    return Clock()


# ── DB / engine helpers ────────────────────────────────────────────────────────
@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


# ── Client factory ─────────────────────────────────────────────────────────────
def _make_client(engine, email: str, password: str, role: str) -> TestClient:
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with Session() as db:
        # Avoid duplicate if fixture is called multiple times in same engine scope
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            user = existing
        else:
            user = User(
                email=email,
                hashed_password=hash_password(password),
                role=role,
                full_name=f"Test {role.capitalize()}",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        token = create_access_token(subject=user.id, role=role)

    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def client(engine):
    """Admin-role TestClient (backward-compatible with all existing tests)."""
    c = _make_client(engine, _ADMIN_EMAIL, _ADMIN_PASSWORD, _ADMIN_ROLE)
    with c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def operator_client(engine):
    """Operator-role TestClient for access-control tests."""
    # Admin must exist first (some fixtures call both)
    _make_client(engine, _ADMIN_EMAIL, _ADMIN_PASSWORD, _ADMIN_ROLE)
    c = _make_client(engine, _OPERATOR_EMAIL, _OPERATOR_PASSWORD, _OPERATOR_ROLE)
    with c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def viewer_client(engine):
    """Viewer-role TestClient for access-control tests."""
    _make_client(engine, _ADMIN_EMAIL, _ADMIN_PASSWORD, _ADMIN_ROLE)
    c = _make_client(engine, _VIEWER_EMAIL, _VIEWER_PASSWORD, _VIEWER_ROLE)
    with c:
        yield c
    app.dependency_overrides.clear()
