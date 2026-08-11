import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

logger = logging.getLogger(__name__)


def _clean(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _create_engine() -> Engine:
    turso_url = _clean(settings.TURSO_DATABASE_URL)
    turso_token = _clean(settings.TURSO_AUTH_TOKEN)
    on_vercel = os.getenv("VERCEL") == "1"

    if turso_url and turso_token:
        import sqlalchemy_libsql  # noqa: F401

        if turso_url.startswith("libsql://"):
            engine_url = f"sqlite+{turso_url}?secure=true"
        elif turso_url.startswith("https://"):
            # Accept https://host → sqlite+libsql://host
            host = turso_url.removeprefix("https://")
            engine_url = f"sqlite+libsql://{host}?secure=true"
        else:
            engine_url = f"sqlite+libsql://{turso_url}?secure=true"

        logger.info("Database: Turso remote (%s)", turso_url)
        return create_engine(
            engine_url,
            connect_args={"auth_token": turso_token},
            poolclass=NullPool,
        )

    if on_vercel:
        raise RuntimeError(
            "Turso is not configured on Vercel. Set TURSO_DATABASE_URL and "
            "TURSO_AUTH_TOKEN in Project → Settings → Environment Variables "
            "(Production), then Redeploy. Do not use local sqlite:/// on Vercel."
        )

    logger.info("Database: local SQLite (%s)", settings.DATABASE_URL)
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
    on_vercel = os.getenv("VERCEL") == "1"
    using_turso = bool(_clean(settings.TURSO_DATABASE_URL) and _clean(settings.TURSO_AUTH_TOKEN))

    if not using_turso and not on_vercel and settings.DATABASE_URL.startswith("sqlite:///"):
        db_path = settings.DATABASE_URL.replace("sqlite:///", "", 1)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    from app import models  # noqa: F401 - ensure models are registered on Base

    Base.metadata.create_all(bind=engine)
