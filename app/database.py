import logging
import os

import turso_serverless
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

logger = logging.getLogger(__name__)


def _clean(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _turso_creator(turso_url: str, turso_token: str):
    def creator():
        conn = turso_serverless.connect(turso_url, auth_token=turso_token)
        # SQLAlchemy's SQLite dialect calls create_function for REGEXP; HTTP driver has none.
        if not hasattr(conn, "create_function"):
            conn.create_function = lambda *args, **kwargs: None  # type: ignore[method-assign]
        return conn

    return creator


def _create_engine() -> Engine:
    turso_url = _clean(settings.TURSO_DATABASE_URL)
    turso_token = _clean(settings.TURSO_AUTH_TOKEN)
    on_vercel = os.getenv("VERCEL") == "1"

    if turso_url and turso_token:
        logger.info("Database: Turso remote (%s)", turso_url)
        return create_engine(
            "sqlite://",
            creator=_turso_creator(turso_url, turso_token),
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
    _ensure_column("products", "last_scrape_error", "TEXT")


def _ensure_column(table: str, column: str, coltype: str) -> None:
    """Add a column to an already-existing table (no-ops if it's already there).

    create_all() only creates missing tables, not missing columns on tables
    that already exist, so schema additions to a live DB need this instead.
    """
    with engine.connect() as conn:
        try:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
            conn.commit()
        except Exception:
            conn.rollback()
