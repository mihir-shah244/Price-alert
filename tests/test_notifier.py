from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models import AlertSent, PriceHistory, Product
from app.notifier import maybe_send_alert


@pytest.fixture(autouse=True)
def _configure_recipient(monkeypatch):
    monkeypatch.setattr(settings, "ALERT_RECIPIENT_EMAIL", "watcher@example.com")


@pytest.fixture()
def sent_emails(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.notifier.send_email",
        lambda subject, html_body, to_addr: calls.append((subject, to_addr)),
    )
    return calls


def _make_product(db_session, target_price=1000.0):
    product = Product(url="https://www.amazon.in/dp/B0X", site="amazon", target_price=target_price)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


def test_first_drop_sends_alert(db_session, sent_emails):
    product = _make_product(db_session)

    sent = maybe_send_alert(db_session, product, new_price=900.0)

    assert sent is True
    assert len(sent_emails) == 1
    assert db_session.query(AlertSent).filter_by(product_id=product.id).count() == 1


def test_repeated_below_target_does_not_resend(db_session, sent_emails):
    product = _make_product(db_session)

    assert maybe_send_alert(db_session, product, new_price=900.0) is True
    assert maybe_send_alert(db_session, product, new_price=850.0) is False

    assert len(sent_emails) == 1
    assert db_session.query(AlertSent).filter_by(product_id=product.id).count() == 1


def test_rebound_then_drop_resends(db_session, sent_emails):
    product = _make_product(db_session)

    assert maybe_send_alert(db_session, product, new_price=900.0) is True

    # Simulate the price recovering above target after the alert was sent.
    last_alert = (
        db_session.query(AlertSent).filter_by(product_id=product.id).order_by(AlertSent.sent_at.desc()).first()
    )
    db_session.add(
        PriceHistory(
            product_id=product.id,
            price=1200.0,
            checked_at=last_alert.sent_at + timedelta(hours=1),
        )
    )
    db_session.commit()

    assert maybe_send_alert(db_session, product, new_price=950.0) is True
    assert len(sent_emails) == 2
    assert db_session.query(AlertSent).filter_by(product_id=product.id).count() == 2


def test_price_above_target_never_sends(db_session, sent_emails):
    product = _make_product(db_session)

    assert maybe_send_alert(db_session, product, new_price=1100.0) is False
    assert len(sent_emails) == 0
