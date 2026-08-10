# Price Alert Dashboard

Track Amazon/Flipkart product URLs, store target prices, and email 
when prices drop below target.

## Tech Stack
- Backend: Python + FastAPI
- Database: SQLite (via SQLAlchemy)
- Scraper: requests + BeautifulSoup (Playwright if JS-rendering needed)
- Scheduler: APScheduler
- Email: smtplib (Gmail SMTP) via env vars
- Frontend: Jinja2 templates + Chart.js for price history

## Project Structure
- `app/main.py` — FastAPI app + routes
- `app/models.py` — SQLAlchemy models (Product, PriceHistory, AlertSent)
- `app/scrapers/amazon.py`, `app/scrapers/flipkart.py` — site-specific scrapers, common interface
- `app/scheduler.py` — periodic price check job
- `app/notifier.py` — email alert logic
- `app/templates/` — dashboard HTML
- `data/app.db` — SQLite file

## Database Schema
- products: id, url, title, site, target_price, current_price, created_at
- price_history: id, product_id, price, checked_at
- alerts_sent: id, product_id, price_at_alert, sent_at

## Conventions
- Each scraper module exposes `scrape(url) -> {title, price}` — keep interface consistent
- Only send one alert per price drop (check alerts_sent before sending)
- Use environment variables for SMTP credentials (.env, never commit)
- Run scraper checks on an interval defined in config, default every 4 hours

## Commands
- Run dev server: `uvicorn app.main:app --reload`
- Run scraper manually: `python -m app.scheduler --once`
- Run tests: `pytest`