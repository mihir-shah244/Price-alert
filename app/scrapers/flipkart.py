# Flipkart's page markup uses hashed/build-generated CSS class names that
# change on every deploy, so CSS selectors for price/title break constantly.
# The schema.org Product JSON-LD block Flipkart embeds for SEO is far more
# stable — use that as the primary source instead.
import json
import re

from bs4 import BeautifulSoup

from app.scrapers.base import ScrapeParseError, fetch

_MRP_RE = re.compile(r'"mrp"\s*:\s*(\d+(?:\.\d+)?)')


def _extract_mrp(html: str) -> float | None:
    """Best-effort strikethrough/MRP lookup from the embedded page state.

    Not part of any stable schema, so this is a bonus value only — a miss
    here just means the progress bar baselines off price history instead.
    """
    match = _MRP_RE.search(html)
    return float(match.group(1)) if match else None


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    script = soup.select_one('script[type="application/ld+json"]')
    if script is None:
        raise ScrapeParseError("Could not find product structured data (ld+json)")

    try:
        data = json.loads(script.get_text())
    except json.JSONDecodeError as exc:
        raise ScrapeParseError(f"Could not parse product structured data: {exc}") from exc

    item = data[0] if isinstance(data, list) else data

    title = item.get("name")
    if not title:
        raise ScrapeParseError("Structured data missing product name")

    price = (item.get("offers") or {}).get("price")
    if price is None:
        raise ScrapeParseError("Structured data missing price")

    images = item.get("image")
    if isinstance(images, list):
        image_url = images[0] if images else None
    else:
        image_url = images

    mrp = _extract_mrp(html)

    return {
        "title": title,
        "price": float(price),
        "original_price": mrp if mrp and mrp > float(price) else None,
        "image_url": image_url,
    }


def scrape(url: str) -> dict:
    return parse_html(fetch(url))
