import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db

settings.SCHEDULER_ENABLED = False

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=_engine)
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def client(db_session, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main as main_module

    monkeypatch.setattr(main_module, "init_db", lambda: None)
    # Never let a test write to the real .env file.
    monkeypatch.setattr(main_module, "update_env_file", lambda updates: None)

    def _override_get_db():
        yield db_session

    main_module.app.dependency_overrides[get_db] = _override_get_db
    with TestClient(main_module.app) as test_client:
        yield test_client
    main_module.app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _isolate_settings():
    """Snapshot mutable settings fields so one test's changes don't leak into the next."""
    fields = [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "ALERT_RECIPIENT_EMAIL",
        "CHECK_INTERVAL_HOURS",
        "SCHEDULER_ENABLED",
        "CRON_SECRET",
    ]
    original = {field: getattr(settings, field) for field in fields}
    yield
    for field, value in original.items():
        setattr(settings, field, value)
