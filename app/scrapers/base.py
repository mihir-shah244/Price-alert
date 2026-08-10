import re

import requests

from app.config import settings

# TODO(playwright fallback): if a site's price is JS-rendered and `fetch()`
# above never contains it in the raw HTML, add `scrape_with_browser(url)`
# implementing the same `{title, price}` contract, gated behind a
# USE_PLAYWRIGHT_FALLBACK config flag. Not needed for v1 — anti-bot blocking
# (see ScrapeBlockedError) is the more common real-world failure mode.


class ScraperError(Exception):
    """Base exception for scraper failures."""


class ScrapeBlockedError(ScraperError):
    """Raised when the site returns a blocked/captcha/unexpected response."""


class ScrapeParseError(ScraperError):
    """Raised when expected content can't be parsed out of the page."""


_PRICE_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def get_headers() -> dict:
    return {
        "User-Agent": settings.SCRAPER_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def fetch(url: str, timeout: float = 10.0) -> str:
    try:
        response = requests.get(url, headers=get_headers(), timeout=timeout)
    except requests.RequestException as exc:
        raise ScraperError(f"Request failed for {url}: {exc}") from exc

    if response.status_code in (403, 429, 503):
        raise ScrapeBlockedError(
            f"Request blocked (status {response.status_code}) for {url}"
        )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise ScraperError(f"Request failed for {url}: {exc}") from exc
    return response.text


def parse_price(text: str) -> float:
    """Extract the first numeric price out of a raw price string.

    Handles currency symbols (₹, $, Rs.), thousands separators, and
    ranges like "₹1,234 - ₹1,999" (takes the first value).
    """
    match = _PRICE_RE.search(text or "")
    if not match:
        raise ScrapeParseError(f"Could not parse a price from: {text!r}")
    return float(match.group(0).replace(",", ""))


def first_text(soup, selectors: list[str]) -> str | None:
    """Return the stripped text of the first selector that matches, or None."""
    for selector in selectors:
        el = soup.select_one(selector)
        if el is not None:
            return el.get_text(strip=True)
    return None


def first_price(soup, selectors: list[str]) -> float | None:
    """Best-effort price lookup: returns None instead of raising when absent.

    Used for optional fields (e.g. original/MRP price) where a missing
    value shouldn't fail the whole scrape.
    """
    text = first_text(soup, selectors)
    if text is None:
        return None
    try:
        return parse_price(text)
    except ScrapeParseError:
        return None


def extract_image(soup, selectors: list[str]) -> str | None:
    """Best-effort product image lookup: site-specific selectors first,
    falling back to the Open Graph image meta tag most product pages set.
    """
    for selector in selectors:
        el = soup.select_one(selector)
        if el is not None:
            src = el.get("src") or el.get("data-old-hires") or el.get("data-src")
            if src:
                return src

    meta = soup.select_one('meta[property="og:image"]')
    if meta is not None:
        return meta.get("content")

    return None
