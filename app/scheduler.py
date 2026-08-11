import argparse
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import PriceHistory, Product
from app.notifier import maybe_send_alert
from app.scrapers import get_scraper_for_url
from app.scrapers.base import ScraperError, friendly_scrape_error

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def check_single_product(db: Session, product: Product) -> bool:
    """Scrape one product, record its price, and fire an alert if warranted.

    Returns True on a successful scrape, False if the scrape failed (logged,
    not raised) so callers can keep checking other products.
    """
    try:
        scraper = get_scraper_for_url(product.url)
        result = scraper(product.url)
    except (ScraperError, ValueError) as exc:
        logger.warning("Scrape failed for product %s (%s): %s", product.id, product.url, exc)
        if isinstance(exc, ScraperError):
            product.last_scrape_error = friendly_scrape_error(exc)
            db.commit()
        return False

    new_price = result["price"]
    product.title = result.get("title") or product.title
    product.current_price = new_price
    product.original_price = result.get("original_price") or product.original_price
    product.image_url = result.get("image_url") or product.image_url
    product.last_scrape_error = None

    db.add(PriceHistory(product_id=product.id, price=new_price))
    db.commit()

    maybe_send_alert(db, product, new_price)
    return True


def run_price_checks(db: Session) -> None:
    for product in db.query(Product).all():
        check_single_product(db, product)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler()

    def _job():
        db = SessionLocal()
        try:
            run_price_checks(db)
        finally:
            db.close()

    _scheduler.add_job(
        _job,
        trigger=IntervalTrigger(hours=settings.CHECK_INTERVAL_HOURS),
        id="price_check_job",
    )
    _scheduler.start()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run price checks for tracked products.")
    parser.add_argument("--once", action="store_true", help="Run a single check pass and exit.")
    args = parser.parse_args()

    init_db()

    if args.once:
        session = SessionLocal()
        try:
            run_price_checks(session)
        finally:
            session.close()
    else:
        parser.error("Only --once is currently supported for manual runs.")
