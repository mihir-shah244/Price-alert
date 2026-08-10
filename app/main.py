import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings, update_env_file
from app.database import get_db, init_db
from app.models import AlertSent, PriceHistory, Product
from app.notifier import send_email
from app.scheduler import check_single_product, run_price_checks, shutdown_scheduler, start_scheduler
from app.scrapers import get_scraper_for_url, get_site_for_url
from app.scrapers.base import ScraperError

logger = logging.getLogger(__name__)

CATEGORY_CHOICES = [
    "Electronics",
    "Smartphones",
    "Tablets",
    "Wearables",
    "E-Readers",
    "Home & Kitchen",
    "Other",
]

CHECK_INTERVAL_CHOICES = [1, 2, 4, 6, 12, 24]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.SCHEDULER_ENABLED:
        start_scheduler()
    yield
    if settings.SCHEDULER_ENABLED:
        shutdown_scheduler()


app = FastAPI(title="Price Alert Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _currency_symbol(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    if domain.endswith(".in") or "flipkart" in domain:
        return "₹"
    return "$"


def _fmt_money(symbol: str, amount: float | None) -> str | None:
    if amount is None:
        return None
    if float(amount).is_integer():
        return f"{symbol}{amount:,.0f}"
    return f"{symbol}{amount:,.2f}"


def _nav_context(db: Session) -> dict:
    return {
        "products_count": db.query(Product).count(),
        "alerts_count": db.query(AlertSent).count(),
    }


def _delivery_status() -> str:
    """Whether alert emails are actually being sent or just logged.

    There's no per-alert delivery tracking (no SMTP send receipt stored),
    so this reflects whether SMTP + a recipient are configured at all.
    """
    if settings.SMTP_USER and settings.SMTP_PASSWORD and settings.ALERT_RECIPIENT_EMAIL:
        return "Sent"
    return "Simulated"


def _build_alert_row(alert: AlertSent, delivery_status: str) -> dict:
    product = alert.product
    symbol = _currency_symbol(product.url)
    savings = product.target_price - alert.price_at_alert

    if savings > 0:
        subtitle = (
            f"Price dropped by {_fmt_money(symbol, savings)} below target price "
            f"({_fmt_money(symbol, product.target_price)})"
        )
    else:
        subtitle = f"Alert triggered at {_fmt_money(symbol, alert.price_at_alert)}"

    return {
        "sent_at": alert.sent_at,
        "product_id": product.id,
        "site": product.site,
        "title": product.title or product.url,
        "subtitle": subtitle,
        "price_at_alert": _fmt_money(symbol, alert.price_at_alert),
        "target_price": _fmt_money(symbol, product.target_price),
        "recipient": settings.ALERT_RECIPIENT_EMAIL or "—",
        "status": delivery_status,
    }


def _build_card(product: Product) -> dict:
    symbol = _currency_symbol(product.url)
    current = product.current_price
    target = product.target_price

    met_target = current is not None and current <= target
    progress_pct = 0
    distance_text = "Not yet checked"

    if current is not None:
        if met_target:
            progress_pct = 100
            distance_text = "Met target!"
        else:
            baseline = product.original_price
            if baseline is None and product.price_history:
                baseline = product.price_history[0].price
            if baseline is not None and baseline > target:
                progress_pct = round(max(0, min(100, (baseline - current) / (baseline - target) * 100)))
            distance_text = f"{_fmt_money(symbol, current - target)} away"

    last_checked = product.price_history[-1].checked_at if product.price_history else None

    return {
        "id": product.id,
        "title": product.title or product.url,
        "url": product.url,
        "site": product.site,
        "category": product.category,
        "image_url": product.image_url,
        "current_price": _fmt_money(symbol, current),
        "original_price": _fmt_money(symbol, product.original_price)
        if product.original_price and (current is None or product.original_price > current)
        else None,
        "target_price": _fmt_money(symbol, target),
        "target_price_raw": target,
        "met_target": met_target,
        "savings": _fmt_money(symbol, target - current) if met_target else None,
        "progress_pct": progress_pct,
        "distance_text": distance_text,
        "last_checked": last_checked,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).order_by(Product.created_at.desc()).all()
    cards = [_build_card(p) for p in products]
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "cards": cards,
            "category_choices": CATEGORY_CHOICES,
            "active_tab": "products",
            **_nav_context(db),
        },
    )


@app.get("/alerts")
def alerts(request: Request, db: Session = Depends(get_db), q: str = "", status: str = "all"):
    delivery_status = _delivery_status()

    query = db.query(AlertSent).join(Product).order_by(AlertSent.sent_at.desc())
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Product.title.ilike(like), Product.site.ilike(like), Product.url.ilike(like))
        )

    status = status.lower()
    rows = [_build_alert_row(a, delivery_status) for a in query.all()]
    if status in ("sent", "simulated"):
        rows = [r for r in rows if r["status"].lower() == status]

    return templates.TemplateResponse(
        request,
        "alerts.html",
        {
            "rows": rows,
            "q": q,
            "status": status or "all",
            "active_tab": "alerts",
            **_nav_context(db),
        },
    )


@app.get("/settings")
def settings_page(request: Request, db: Session = Depends(get_db), saved: str = "", test: str = ""):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active_tab": "settings",
            "settings": settings,
            "interval_choices": CHECK_INTERVAL_CHOICES,
            "has_password": bool(settings.SMTP_PASSWORD),
            "saved": saved,
            "test_result": test,
            **_nav_context(db),
        },
    )


@app.post("/settings")
def save_settings(
    check_interval_hours: float = Form(...),
    auto_scraper: str | None = Form(None),
    alert_recipient_email: str = Form(""),
    smtp_host: str = Form(""),
    smtp_port: int = Form(465),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
):
    settings.CHECK_INTERVAL_HOURS = check_interval_hours
    settings.SCHEDULER_ENABLED = bool(auto_scraper)
    settings.ALERT_RECIPIENT_EMAIL = alert_recipient_email
    settings.SMTP_HOST = smtp_host
    settings.SMTP_PORT = smtp_port
    settings.SMTP_USER = smtp_user
    if smtp_password:
        settings.SMTP_PASSWORD = smtp_password

    env_updates = {
        "CHECK_INTERVAL_HOURS": str(check_interval_hours),
        "SCHEDULER_ENABLED": str(settings.SCHEDULER_ENABLED).lower(),
        "ALERT_RECIPIENT_EMAIL": alert_recipient_email,
        "SMTP_HOST": smtp_host,
        "SMTP_PORT": str(smtp_port),
        "SMTP_USER": smtp_user,
    }
    if smtp_password:
        env_updates["SMTP_PASSWORD"] = smtp_password
    update_env_file(env_updates)

    shutdown_scheduler()
    if settings.SCHEDULER_ENABLED:
        start_scheduler()

    return RedirectResponse(url="/settings?saved=1", status_code=303)


@app.post("/settings/test-email")
def send_test_email():
    if not (settings.SMTP_USER and settings.SMTP_PASSWORD and settings.ALERT_RECIPIENT_EMAIL):
        return RedirectResponse(url="/settings?test=error", status_code=303)

    try:
        send_email(
            subject="PriceAlertHub test alert",
            html_body="<p>This is a test alert email from PriceAlertHub. Your SMTP settings are working.</p>",
            to_addr=settings.ALERT_RECIPIENT_EMAIL,
        )
    except Exception as exc:
        logger.warning("Test email failed: %s", exc)
        return RedirectResponse(url="/settings?test=error", status_code=303)

    return RedirectResponse(url="/settings?test=sent", status_code=303)


@app.post("/products")
def add_product(
    url: str = Form(...),
    target_price: float = Form(...),
    category: str = Form("Uncategorized"),
    db: Session = Depends(get_db),
):
    try:
        site = get_site_for_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    product = Product(
        url=url,
        site=site,
        category=category or "Uncategorized",
        target_price=target_price,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    try:
        scraper = get_scraper_for_url(url)
        result = scraper(url)
        product.title = result.get("title")
        product.current_price = result.get("price")
        product.original_price = result.get("original_price")
        product.image_url = result.get("image_url")
        db.add(PriceHistory(product_id=product.id, price=product.current_price))
        db.commit()
    except ScraperError:
        pass  # next scheduled run will retry

    return RedirectResponse(url="/", status_code=303)


@app.get("/products/{product_id}")
def product_detail(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return templates.TemplateResponse(
        request, "product_detail.html", {"product": product, **_nav_context(db)}
    )


@app.get("/products/{product_id}/history")
def product_history(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    history = (
        db.query(PriceHistory)
        .filter(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.checked_at.asc())
        .all()
    )
    return [
        {"price": h.price, "checked_at": h.checked_at.isoformat()} for h in history
    ]


@app.post("/products/{product_id}/edit")
def edit_product(
    product_id: int,
    target_price: float = Form(...),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product.target_price = target_price
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/products/{product_id}/check")
def check_product_now(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    check_single_product(db, product)
    return RedirectResponse(url="/", status_code=303)


@app.post("/products/check-all")
def check_all_products(db: Session = Depends(get_db), next: str = Form("/")):
    run_price_checks(db)
    target = next if next.startswith("/") else "/"
    return RedirectResponse(url=target, status_code=303)


@app.post("/products/{product_id}/delete")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    return RedirectResponse(url="/", status_code=303)
