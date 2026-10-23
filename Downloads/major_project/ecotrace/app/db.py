"""Database setup: SQLAlchemy 2.0 declarative base, engine, session factory.

DATABASE_URL is read from the environment variable of the same name.
Default is SQLite (dev). Set DATABASE_URL=postgresql+psycopg2://... for Postgres.

Models stay Postgres-compatible (no SQLite-only types). All datetimes naive UTC.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DEFAULT_URL = "sqlite:///./ecotrace.db"
DATABASE_URL: str = os.getenv("DATABASE_URL", _DEFAULT_URL)

# SQLite requires check_same_thread=False; Postgres does not support it → pass only when needed.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, echo=False)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables (idempotent). Used by seed scripts and tests."""
    from app import models  # noqa: F401  register models on Base
    Base.metadata.create_all(bind=engine)


def drop_db():
    """Drop all tables. Used by seed --reset."""
    from app import models  # noqa: F401
    Base.metadata.drop_all(bind=engine)
