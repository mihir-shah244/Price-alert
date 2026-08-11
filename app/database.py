import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings


def _create_engine() -> Engine:
    if settings.use_turso:
        # Registers the sqlite+libsql dialect. Required on Vercel (Linux).
        import sqlalchemy_libsql  # noqa: F401

        turso_url = settings.TURSO_DATABASE_URL.strip()
        # Official pattern: sqlite+libsql://host... when TURSO_DATABASE_URL is libsql://host
        engine_url = f"sqlite+{turso_url}?secure=true"
        return create_engine(
            engine_url,
            connect_args={"auth_token": settings.TURSO_AUTH_TOKEN},
        )

    return create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
    )


engine = _create_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    if not settings.use_turso and settings.DATABASE_URL.startswith("sqlite:///"):
        db_path = settings.DATABASE_URL.replace("sqlite:///", "", 1)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    from app import models  # noqa: F401 - ensure models are registered on Base

    Base.metadata.create_all(bind=engine)
