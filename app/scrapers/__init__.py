from typing import Callable
from urllib.parse import urlparse

from app.scrapers import amazon, flipkart

_SITE_SCRAPERS: dict[str, Callable[[str], dict]] = {
    "amazon": amazon.scrape,
    "flipkart": flipkart.scrape,
}


def get_site_for_url(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    if "amazon." in domain:
        return "amazon"
    if "flipkart." in domain:
        return "flipkart"
    raise ValueError(f"Unsupported site for URL: {url}")


def get_scraper_for_url(url: str) -> Callable[[str], dict]:
    site = get_site_for_url(url)
    return _SITE_SCRAPERS[site]
