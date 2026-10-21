"""Database setup: SQLAlchemy 2.0 declarative base, dev SQLite engine, session factory.

Models stay Postgres-compatible (no SQLite-only types). All datetimes naive UTC.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///./ecotrace.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

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
    """Create all tables on the dev engine (idempotent)."""
    from app import models  # noqa: F401  ensure models registered on Base
    Base.metadata.create_all(bind=engine)


def drop_db():
    """Drop all tables on the dev engine."""
    from app import models  # noqa: F401
    Base.metadata.drop_all(bind=engine)
