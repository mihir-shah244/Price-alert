import re
import time
from typing import Callable

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


class ScraperError(Exception):
    """Base exception for scraper failures."""


class ScrapeBlockedError(ScraperError):
    """Raised when the site returns a blocked/captcha/unexpected response."""


class ScrapeParseError(ScraperError):
    """Raised when expected content can't be parsed out of the page."""


_PRICE_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def get_headers() -> dict:
    # No User-Agent override here: `impersonate="chrome"` in fetch() already
    # sends a matching Chrome UA + TLS/HTTP2 fingerprint, and overriding just
    # the UA string would desync that pair — a mismatch bot-detection looks for.
    return {"Accept-Language": "en-US,en;q=0.9"}


def fetch(url: str, timeout: float = 10.0) -> str:
    try:
        response = requests.get(
            url, headers=get_headers(), timeout=timeout, impersonate="chrome"
        )
    except RequestException as exc:
        raise ScraperError(f"Request failed for {url}: {exc}") from exc

    if response.status_code in (403, 429, 503):
        raise ScrapeBlockedError(
            f"Request blocked (status {response.status_code}) for {url}"
        )
    try:
        response.raise_for_status()
    except RequestException as exc:
        raise ScraperError(f"Request failed for {url}: {exc}") from exc
    return response.text


def scrape_with_retry(
    scraper: Callable[[str], dict], url: str, attempts: int = 2, delay: float = 1.5
) -> dict:
    """Run `scraper(url)`, retrying on ScraperError up to `attempts` times.

    Sites like Amazon/Flipkart occasionally block or hiccup on a single
    request; a short retry gives a real second chance without the request
    hanging for long. Re-raises the last error if every attempt fails.
    """
    last_error: ScraperError | None = None
    for attempt in range(attempts):
        try:
            return scraper(url)
        except ScraperError as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(delay)
    assert last_error is not None
    raise last_error


def friendly_scrape_error(exc: ScraperError) -> str:
    """Human-readable status for the UI, distinct from the raw exception text."""
    if isinstance(exc, ScrapeBlockedError):
        return "Site blocked the price check - will retry automatically"
    if isinstance(exc, ScrapeParseError):
        return "Couldn't read the price from this page - will retry automatically"
    return "Price check failed - will retry automatically"


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
