import pytest

from app.scrapers import get_site_for_url
from app.scrapers.amazon import parse_html as amazon_parse_html
from app.scrapers.base import ScrapeParseError, parse_price
from app.scrapers.flipkart import parse_html as flipkart_parse_html


@pytest.mark.parametrize(
    "text,expected",
    [
        ("₹1,234", 1234.0),
        ("$1,234.56", 1234.56),
        ("Rs. 999", 999.0),
        ("₹1,234 - ₹1,999", 1234.0),
        ("1999", 1999.0),
    ],
)
def test_parse_price_valid(text, expected):
    assert parse_price(text) == expected


def test_parse_price_invalid_raises():
    with pytest.raises(ScrapeParseError):
        parse_price("no digits here")


def test_get_site_for_url():
    assert get_site_for_url("https://www.amazon.in/dp/B0X") == "amazon"
    assert get_site_for_url("https://www.flipkart.com/p/xyz") == "flipkart"
    with pytest.raises(ValueError):
        get_site_for_url("https://www.example.com/product")


def test_amazon_parse_html():
    html = """
    <html>
      <span id="productTitle"> Cool Gadget </span>
      <span class="a-price"><span class="a-offscreen">₹1,999</span></span>
    </html>
    """
    result = amazon_parse_html(html)
    assert result["title"] == "Cool Gadget"
    assert result["price"] == 1999.0
    assert result["original_price"] is None
    assert result["image_url"] is None


def test_amazon_parse_html_with_original_price_and_image():
    html = """
    <html>
      <span id="productTitle">Cool Gadget</span>
      <span class="a-price"><span class="a-offscreen">₹1,999</span></span>
      <span class="a-price a-text-price"><span class="a-offscreen">₹2,499</span></span>
      <img id="landingImage" src="https://example.com/gadget.jpg" />
    </html>
    """
    result = amazon_parse_html(html)
    assert result["original_price"] == 2499.0
    assert result["image_url"] == "https://example.com/gadget.jpg"


def test_amazon_parse_html_missing_title_raises():
    html = '<html><span class="a-price"><span class="a-offscreen">₹1,999</span></span></html>'
    with pytest.raises(ScrapeParseError):
        amazon_parse_html(html)


def _flipkart_ld_json(*, price=2499, mrp=None, image="https://example.com/widget.jpg"):
    import json

    payload = {
        "name": "Great Widget",
        "image": [image] if image else [],
        "offers": {"price": price, "priceCurrency": "INR"},
    }
    body = json.dumps(payload)
    mrp_blob = f'{{"mrp":{mrp}}}' if mrp is not None else ""
    return f"""
    <html>
      <script type="application/ld+json">{body}</script>
      <script>{mrp_blob}</script>
    </html>
    """


def test_flipkart_parse_html():
    result = flipkart_parse_html(_flipkart_ld_json(image=None))
    assert result["title"] == "Great Widget"
    assert result["price"] == 2499.0
    assert result["original_price"] is None
    assert result["image_url"] is None


def test_flipkart_parse_html_with_original_price_and_image():
    result = flipkart_parse_html(_flipkart_ld_json(price=2499, mrp=2999))
    assert result["original_price"] == 2999.0
    assert result["image_url"] == "https://example.com/widget.jpg"


def test_flipkart_parse_html_missing_price_raises():
    html = """
    <html>
      <script type="application/ld+json">{"name": "Great Widget"}</script>
    </html>
    """
    with pytest.raises(ScrapeParseError):
        flipkart_parse_html(html)


def test_flipkart_parse_html_missing_ld_json_raises():
    html = "<html><span>Great Widget</span></html>"
    with pytest.raises(ScrapeParseError):
        flipkart_parse_html(html)
