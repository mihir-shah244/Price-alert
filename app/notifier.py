import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AlertSent, PriceHistory, Product

_TEMPLATES_DIR = "app/templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR))


def send_email(subject: str, html_body: str, to_addr: str) -> None:
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.SMTP_USER
    message["To"] = to_addr
    message.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_USER, [to_addr], message.as_string())


def _has_rebounded_since(db: Session, product_id: int, target_price: float, since) -> bool:
    stmt = select(PriceHistory).where(
        PriceHistory.product_id == product_id,
        PriceHistory.checked_at > since,
        PriceHistory.price > target_price,
    )
    return db.execute(stmt).first() is not None


def maybe_send_alert(db: Session, product: Product, new_price: float) -> bool:
    """Send a price-drop alert if this is a fresh below-target streak.

    Re-arm-on-rebound dedup: one alert per continuous below-target streak.
    A new alert only fires again once the price has risen back above
    target and then dropped below target again.
    """
    if new_price > product.target_price:
        return False

    last_alert = (
        db.query(AlertSent)
        .filter(AlertSent.product_id == product.id)
        .order_by(AlertSent.sent_at.desc())
        .first()
    )

    if last_alert is not None and not _has_rebounded_since(
        db, product.id, product.target_price, last_alert.sent_at
    ):
        return False

    if settings.ALERT_RECIPIENT_EMAIL:
        template = _env.get_template("email/alert.html")
        html_body = template.render(
            title=product.title or product.url,
            url=product.url,
            current_price=new_price,
            target_price=product.target_price,
        )
        send_email(
            subject=f"Price drop: {product.title or product.url}",
            html_body=html_body,
            to_addr=settings.ALERT_RECIPIENT_EMAIL,
        )

    db.add(AlertSent(product_id=product.id, price_at_alert=new_price))
    db.commit()
    return True
