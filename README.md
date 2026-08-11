# Price Alert Dashboard

Track Amazon/Flipkart product URLs, store target prices, and email when prices drop below target. See [docs/claude.md](docs/claude.md) for the full spec.

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in SMTP_USER / SMTP_PASSWORD (Gmail App Password) / ALERT_RECIPIENT_EMAIL
```

## Commands

- Run dev server: `uvicorn app.main:app --reload`
- Run scraper manually: `python -m app.scheduler --once`
- Run tests: `pytest`

The dashboard is served at `http://127.0.0.1:8000/`. Adding a product attempts an immediate scrape; if it fails (site blocked, layout changed), the product is still added and picked up on the next scheduled check (default every `CHECK_INTERVAL_HOURS` hours, set in `.env`).

## Deploy on Vercel + Turso

Local SQLite (`DATABASE_URL=sqlite:///data/app.db`) does not work on Vercel (read-only filesystem). Use Turso Cloud:

1. Create a Turso database and auth token.
2. In Vercel → Project → Settings → Environment Variables, set:
   - `TURSO_DATABASE_URL` — e.g. `libsql://your-db.turso.io`
   - `TURSO_AUTH_TOKEN`
   - `SCHEDULER_ENABLED=false`
   - `CRON_SECRET` — long random string (Vercel Cron sends `Authorization: Bearer <CRON_SECRET>`)
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_RECIPIENT_EMAIL`
3. Redeploy. Cron hits `GET /api/cron/check-prices` every 4 hours (`vercel.json`).

Leave `TURSO_*` empty to use local SQLite (`DATABASE_URL`). With Turso set, the app uses `turso_serverless` (HTTP) — works on Windows and Vercel.

## Notes

- Scrapers (`app/scrapers/amazon.py`, `app/scrapers/flipkart.py`) use `requests` + `BeautifulSoup` against static HTML. Selectors are best-effort and may need updating if the sites change markup. A Playwright-based fallback for JS-rendered pricing is stubbed as a TODO in `app/scrapers/base.py` but not implemented. Alongside `{title, price}`, scrapers also best-effort extract `original_price` (strikethrough MRP) and `image_url` — both are optional and `None` when the page doesn't expose them.
- Alerts are deduplicated with a "re-arm on rebound" rule: one email per continuous below-target streak. A product only alerts again after its price rises back above target and later drops below target once more.
- The dashboard ("Products & Alerts" tab) is a card grid: site/category badges, current vs. strikethrough original price, an editable target threshold (pencil icon), a progress bar toward target, a green "met target" banner, and per-card "Check now" / delete actions, plus a "Check All Prices" action in the top bar. The "Alert Logs" and "Settings & Scraper" tabs are placeholders for now — per-product price history is on each product's detail page.
