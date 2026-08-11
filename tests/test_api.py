import pytest

from app.models import AlertSent, PriceHistory, Product


def _seed_product(db_session):
    product = Product(
        url="https://www.amazon.in/dp/B0X",
        site="amazon",
        title="Cool Gadget",
        target_price=1000.0,
        current_price=1200.0,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    db_session.add(PriceHistory(product_id=product.id, price=1200.0))
    db_session.commit()
    return product


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_dashboard_lists_products(client, db_session):
    _seed_product(db_session)
    r = client.get("/")
    assert r.status_code == 200
    assert "Cool Gadget" in r.text


def test_add_product_unsupported_site_returns_400(client):
    r = client.post("/products", data={"url": "https://example.com/p", "target_price": "10"})
    assert r.status_code == 400


def test_add_product_scrape_failure_still_creates_product(client, db_session, monkeypatch):
    from app.scrapers.base import ScraperError

    def _boom(url):
        raise ScraperError("network down")

    monkeypatch.setattr("app.main.get_scraper_for_url", lambda url: _boom)

    r = client.post(
        "/products",
        data={"url": "https://www.amazon.in/dp/B0Y", "target_price": "500"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    product = db_session.query(Product).filter_by(url="https://www.amazon.in/dp/B0Y").first()
    assert product is not None
    assert product.current_price is None


def test_add_product_success_populates_price(client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.main.get_scraper_for_url",
        lambda url: (lambda u: {"title": "Nice Thing", "price": 750.0}),
    )

    r = client.post(
        "/products",
        data={"url": "https://www.flipkart.com/p/abc", "target_price": "800"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    product = db_session.query(Product).filter_by(url="https://www.flipkart.com/p/abc").first()
    assert product.title == "Nice Thing"
    assert product.current_price == 750.0
    assert len(product.price_history) == 1


def test_product_detail_and_history(client, db_session):
    product = _seed_product(db_session)

    r = client.get(f"/products/{product.id}")
    assert r.status_code == 200

    r = client.get(f"/products/{product.id}/history")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["price"] == 1200.0


def test_product_detail_404(client):
    r = client.get("/products/999")
    assert r.status_code == 404


def test_edit_product(client, db_session):
    product = _seed_product(db_session)
    r = client.post(f"/products/{product.id}/edit", data={"target_price": "555"}, follow_redirects=False)
    assert r.status_code == 303
    db_session.refresh(product)
    assert product.target_price == 555.0


def test_delete_product(client, db_session):
    product = _seed_product(db_session)
    r = client.post(f"/products/{product.id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert db_session.query(Product).filter_by(id=product.id).first() is None


def test_add_product_with_category_uses_scraped_title(client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.main.get_scraper_for_url",
        lambda url: (lambda u: {"title": "Scraped Name", "price": 100.0}),
    )

    r = client.post(
        "/products",
        data={
            "url": "https://www.flipkart.com/p/manual",
            "target_price": "90",
            "category": "Wearables",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    product = db_session.query(Product).filter_by(url="https://www.flipkart.com/p/manual").first()
    assert product.category == "Wearables"
    assert product.title == "Scraped Name"


def test_add_product_defaults_category_when_omitted(client, db_session):
    r = client.post(
        "/products",
        data={"url": "https://www.amazon.in/dp/NOCAT", "target_price": "10"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    product = db_session.query(Product).filter_by(url="https://www.amazon.in/dp/NOCAT").first()
    assert product.category == "Uncategorized"


def test_check_product_now(client, db_session, monkeypatch):
    product = _seed_product(db_session)
    monkeypatch.setattr(
        "app.scheduler.get_scraper_for_url",
        lambda url: (lambda u: {"title": "Cool Gadget", "price": 999.0}),
    )

    r = client.post(f"/products/{product.id}/check", follow_redirects=False)
    assert r.status_code == 303

    db_session.refresh(product)
    assert product.current_price == 999.0


def test_check_product_now_404(client):
    r = client.post("/products/999/check")
    assert r.status_code == 404


def test_check_all_products(client, db_session, monkeypatch):
    _seed_product(db_session)
    monkeypatch.setattr(
        "app.scheduler.get_scraper_for_url",
        lambda url: (lambda u: {"title": "Cool Gadget", "price": 111.0}),
    )

    r = client.post("/products/check-all", follow_redirects=False)
    assert r.status_code == 303

    product = db_session.query(Product).first()
    assert product.current_price == 111.0


@pytest.mark.parametrize("path", ["/alerts", "/settings"])
def test_placeholder_tabs_render(client, path):
    r = client.get(path)
    assert r.status_code == 200


def _seed_alert(db_session, title="Cool Gadget", site="amazon", target_price=1000.0, price_at_alert=900.0):
    product = Product(
        url=f"https://www.{site}.in/dp/{title.replace(' ', '')}",
        site=site,
        title=title,
        target_price=target_price,
        current_price=price_at_alert,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    alert = AlertSent(product_id=product.id, price_at_alert=price_at_alert)
    db_session.add(alert)
    db_session.commit()
    return product, alert


def test_alerts_page_lists_sent_alerts(client, db_session):
    _seed_alert(db_session, title="Cool Gadget")
    r = client.get("/alerts")
    assert r.status_code == 200
    assert "Cool Gadget" in r.text
    assert "below target price" in r.text
    # No SMTP credentials configured in tests, so alerts are logged but not actually sent.
    assert "Simulated" in r.text


def test_alerts_page_search_filters_by_title(client, db_session):
    _seed_alert(db_session, title="Cool Gadget")
    _seed_alert(db_session, title="Other Widget")

    r = client.get("/alerts", params={"q": "Cool"})
    assert "Cool Gadget" in r.text
    assert "Other Widget" not in r.text


def test_alerts_page_status_filter_excludes_when_mismatched(client, db_session):
    _seed_alert(db_session, title="Cool Gadget")

    r = client.get("/alerts", params={"status": "sent"})
    assert "Cool Gadget" not in r.text

    r = client.get("/alerts", params={"status": "simulated"})
    assert "Cool Gadget" in r.text


def test_settings_page_renders_current_values(client):
    from app.config import settings

    settings.CHECK_INTERVAL_HOURS = 6
    settings.ALERT_RECIPIENT_EMAIL = "watcher@example.com"

    r = client.get("/settings")
    assert r.status_code == 200
    assert "watcher@example.com" in r.text
    assert "Every 6 Hours" in r.text


def test_save_settings_updates_in_memory_settings(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr("app.main.start_scheduler", lambda: None)
    monkeypatch.setattr("app.main.shutdown_scheduler", lambda: None)

    r = client.post(
        "/settings",
        data={
            "check_interval_hours": "12",
            "alert_recipient_email": "new@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_user": "bot@example.com",
            "smtp_password": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/settings?saved=1"

    assert settings.CHECK_INTERVAL_HOURS == 12
    assert settings.ALERT_RECIPIENT_EMAIL == "new@example.com"
    assert settings.SMTP_HOST == "smtp.example.com"
    assert settings.SMTP_PORT == 587
    assert settings.SCHEDULER_ENABLED is False  # auto_scraper checkbox omitted


def test_save_settings_blank_password_keeps_existing(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr("app.main.start_scheduler", lambda: None)
    monkeypatch.setattr("app.main.shutdown_scheduler", lambda: None)
    settings.SMTP_PASSWORD = "existing-app-password"

    client.post(
        "/settings",
        data={
            "check_interval_hours": "4",
            "smtp_password": "",
        },
        follow_redirects=False,
    )

    assert settings.SMTP_PASSWORD == "existing-app-password"


def test_save_settings_enables_scheduler(client, monkeypatch):
    from app.config import settings

    start_calls = []
    monkeypatch.setattr("app.main.start_scheduler", lambda: start_calls.append(True))
    monkeypatch.setattr("app.main.shutdown_scheduler", lambda: None)

    client.post(
        "/settings",
        data={"check_interval_hours": "4", "auto_scraper": "on"},
        follow_redirects=False,
    )

    assert settings.SCHEDULER_ENABLED is True
    assert start_calls == [True]


def test_send_test_email_without_smtp_configured_errors(client):
    from app.config import settings

    settings.SMTP_USER = ""
    settings.SMTP_PASSWORD = ""

    r = client.post("/settings/test-email", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/settings?test=error"


def test_send_test_email_success(client, monkeypatch):
    from app.config import settings

    settings.SMTP_USER = "bot@example.com"
    settings.SMTP_PASSWORD = "secret"
    settings.ALERT_RECIPIENT_EMAIL = "watcher@example.com"

    sent = []
    monkeypatch.setattr(
        "app.main.send_email",
        lambda subject, html_body, to_addr: sent.append((subject, to_addr)),
    )

    r = client.post("/settings/test-email", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/settings?test=sent"
    assert sent == [("PriceAlertHub test alert", "watcher@example.com")]


def test_check_all_products_redirects_to_next(client, db_session):
    _seed_product(db_session)
    r = client.post("/products/check-all", data={"next": "/settings"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/settings"


def test_cron_check_prices_requires_secret(client):
    from app.config import settings

    settings.CRON_SECRET = "test-cron-secret"
    r = client.get("/api/cron/check-prices")
    assert r.status_code == 401


def test_cron_check_prices_unauthorized(client):
    from app.config import settings

    settings.CRON_SECRET = "test-cron-secret"
    r = client.get("/api/cron/check-prices", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_cron_check_prices_ok(client, db_session, monkeypatch):
    from app.config import settings

    settings.CRON_SECRET = "test-cron-secret"
    called = []
    monkeypatch.setattr("app.main.run_price_checks", lambda db: called.append(True))

    r = client.get(
        "/api/cron/check-prices",
        headers={"Authorization": "Bearer test-cron-secret"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert called == [True]

