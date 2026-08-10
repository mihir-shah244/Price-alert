from bs4 import BeautifulSoup

from app.scrapers.base import (
    ScrapeParseError,
    extract_image,
    fetch,
    first_price,
    parse_price,
)

_PRICE_SELECTORS = [
    "span.a-price .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
]
# Strikethrough "M.R.P." / list price shown next to the offer price.
_ORIGINAL_PRICE_SELECTORS = [
    "span.a-price.a-text-price .a-offscreen",
    "#priceblock_ourprice ~ .a-text-strike",
]
_IMAGE_SELECTORS = ["#landingImage", "#imgBlkFront"]


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("#productTitle")
    if title_el is None:
        raise ScrapeParseError("Could not find product title (#productTitle)")
    title = title_el.get_text(strip=True)

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
