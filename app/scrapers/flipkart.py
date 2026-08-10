# NOTE: Flipkart changes its markup/class names frequently — these selectors
# are best-effort and may need updating if scraping starts failing.
from bs4 import BeautifulSoup

from app.scrapers.base import (
    ScrapeParseError,
    extract_image,
    fetch,
    first_price,
    parse_price,
)

_TITLE_SELECTORS = ["span.B_NuCI", "span.VU-ZEz", "h1"]
_PRICE_SELECTORS = ["div._30jeq3", "div.Nx9bqj"]
_ORIGINAL_PRICE_SELECTORS = ["div._3I9_wc", "div.yRaY8j"]
_IMAGE_SELECTORS = ["img._396cs4", "img._2r_T1I"]


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    title = None
    for selector in _TITLE_SELECTORS:
        el = soup.select_one(selector)
        if el is not None:
            title = el.get_text(strip=True)
            break
    if title is None:
        raise ScrapeParseError("Could not find product title")

    price_text = None
    for selector in _PRICE_SELECTORS:
        el = soup.select_one(selector)
        if el is not None:
            price_text = el.get_text(strip=True)
            break
    if price_text is None:
        raise ScrapeParseError("Could not find a price element on the page")

    return {
        "title": title,
        "price": parse_price(price_text),
        "original_price": first_price(soup, _ORIGINAL_PRICE_SELECTORS),
        "image_url": extract_image(soup, _IMAGE_SELECTORS),
    }


def scrape(url: str) -> dict:
    return parse_html(fetch(url))
