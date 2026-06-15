"""Extract structured data from Immowelt's embedded JSON.

The site embeds server-side data in a script tag:
  <script id="__UFRN_FETCHER__">
    window["__UFRN_FETCHER__"] = JSON.parse("...");
  </script>

The parsed JSON has the structure:
  {"data": {"/immobilienpreise/{path}": {"pricePageContext": {...}, ...}}}

Consumer functions in this module take `page_data` (the inner value keyed by
URL path) rather than the root object.
"""

import json
import logging
import re
from typing import Any, Optional
from urllib.parse import urljoin

from scraper.config import ACCURACY_MAP, BASE_URL
from scraper.fetcher import fetch_page

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level JSON extraction
# ---------------------------------------------------------------------------

SCRIPT_PATTERN = re.compile(
    r'<script[^>]*id="__UFRN_FETCHER__"[^>]*>(.*?)</script>',
    re.DOTALL,
)

# Match: window["__UFRN_FETCHER__"] = JSON.parse("...");
# The argument is a JS string literal — handle escaped quotes (\") inside it.
FETCHER_PATTERN = re.compile(
    r'__UFRN_FETCHER__">window\[\s*"__UFRN_FETCHER__"\s*\]\s*=\s*JSON\.parse\(\s*"((?:[^"\\]|\\.)*)"\s*\)',
)


def _unescape_js_string(s: str) -> str:
    """Unescape a JavaScript string literal (e.g. \\" -> ", \\n -> newline)."""
    return s.encode("utf-8").decode("unicode_escape")


def parse_ufrn_json(html: str) -> Optional[dict[str, Any]]:
    """Extract and parse the __UFRN_FETCHER__ JSON blob from the page HTML.

    Returns the full parsed object (the value of ``JSON.parse(...)``), or
    ``None`` if the script tag or JSON cannot be read.
    """
    # Find script tag
    m = SCRIPT_PATTERN.search(html)
    if not m:
        logger.warning("__UFRN_FETCHER__ script tag not found")
        return None

    # Extract the JSON.parse() argument from the script content
    m2 = FETCHER_PATTERN.search(html)
    if not m2:
        logger.warning("JSON.parse() pattern not found in __UFRN_FETCHER__")
        return None

    raw = m2.group(1)
    try:
        json_str = _unescape_js_string(raw)
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse __UFRN_FETCHER__ JSON: %s", exc)
        return None


def extract_page_data(
    data_root: dict[str, Any],
    url_path: str,
) -> Optional[dict[str, Any]]:
    """Navigate into ``data_root["data"][url_path]``.

    ``url_path`` should be the path component of the fetched URL (e.g.
    ``/immobilienpreise/deutschland``).  Returns ``None`` if the path key is
    absent.
    """
    try:
        inner = data_root["data"]
        return inner[url_path]
    except (KeyError, TypeError) as exc:
        logger.warning("Page data not found for path %s: %s", url_path, exc)
        return None


# ---------------------------------------------------------------------------
# Price extraction helpers
# ---------------------------------------------------------------------------


def _extract_price_block(
    prices_container: dict[str, Any],
    transaction_type: str,
) -> dict[str, Any]:
    """Extract the three price entries (house, apartment, hybrid) for one
    transaction type.
    """
    tx = prices_container.get(transaction_type, {})
    return {
        prop: _clean_price_entry(tx.get(prop, {}), prop)
        for prop in ("house", "apartment", "hybrid")
    }


def _clean_price_entry(
    entry: dict[str, Any],
    property_type: str,
) -> dict[str, Any]:
    """Normalize a price entry."""
    accuracy_raw = entry.get("accuracy")
    return {
        "property_type": property_type,
        "avg_price": entry.get("average"),
        "min_price": entry.get("low"),
        "max_price": entry.get("high"),
        "accuracy": ACCURACY_MAP.get(accuracy_raw, str(accuracy_raw)),
        "data_date": entry.get("date"),
    }


def extract_current_prices(page_data: dict[str, Any]) -> dict[str, Any]:
    """Extract current price data (sell + rent if available)."""
    result: dict[str, Any] = {"kauf": {}, "miete": {}}

    prices_container = page_data.get("prices", {})
    if not prices_container:
        return result

    if "sell" in prices_container:
        result["kauf"] = _extract_price_block(prices_container, "sell")
    if "rent" in prices_container:
        result["miete"] = _extract_price_block(prices_container, "rent")

    return result


# ---------------------------------------------------------------------------
# Historical indices
# ---------------------------------------------------------------------------


def extract_indices(page_data: dict[str, Any]) -> dict[str, Any]:
    """Extract historical price indices."""
    indices = page_data.get("indices", {})
    result: dict[str, Any] = {}

    for prop_type in ("apartment", "house"):
        idx_data = indices.get(prop_type)
        if not idx_data:
            continue

        # Yearly evolution values
        yearly = idx_data.get("priceEvolutionValues", [])
        result[f"{prop_type}_yearly"] = [
            {
                "year": int(item["date"]) if item.get("date") else None,
                "avg_price": item.get("price"),
                "change_vs_previous_pct": round(item.get("evolution", 0), 2)
                if item.get("evolution")
                else None,
            }
            for item in yearly
        ]

        # Short-term evolution
        evolution = idx_data.get("priceEvolution", [])
        result[f"{prop_type}_evolution"] = [
            {
                "period": f"{e.get('timePeriodValue', '?')}{e.get('timePeriodUnit', '?')}",
                "change_pct": e.get("percentagePriceEvolution"),
                "level": e.get("priceEvolutionLevel"),
            }
            for e in evolution
        ]

    return result


# ---------------------------------------------------------------------------
# Place / crawling links
# ---------------------------------------------------------------------------


def extract_place_info(page_data: dict[str, Any]) -> dict[str, Any]:
    """Extract current place info from pricePageContext."""
    ctx = page_data.get("pricePageContext", {})
    place = ctx.get("place", {})
    parents = place.get("parents", {})

    state_name = None
    region = parents.get("region", {}) if parents else {}
    if region:
        state_name = region.get("name", {}).get("display")

    return {
        "id": place.get("id"),
        "name": place.get("name", {}).get("display"),
        "slug": place.get("slug"),
        "level": place.get("type"),  # country / region / city / neighborhood / street
        "state_name": state_name,
        "administrative_code": place.get("administrativeCode"),
    }


def extract_place_links(page_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract links to related places for crawling.

    Returns a list of dicts with keys: place_type, url, place_name, price,
    box_title.
    """
    boxes = page_data.get("placeLinkBoxes", [])
    links: list[dict[str, Any]] = []

    for box in boxes:
        box_links = box.get("links", [])
        for link in box_links:
            url = link.get("url")
            if not url:
                continue
            links.append({
                "place_type": link.get("placeType"),
                "url": urljoin(BASE_URL, url),
                "place_name": link.get("placeName"),
                "price": link.get("price"),
                "box_title": box.get("titleI18nKey"),
            })

    return links


def extract_serp_links(page_data: dict[str, Any]) -> dict[str, Any]:
    """Extract SERP links with active listing counts."""
    serp = page_data.get("serpLinks", {})
    result = {}

    for key, mapping in (("buyHouse", "kauf_haus"), ("buyApartment", "kauf_wohnung")):
        entry = serp.get(key, {})
        if entry:
            result[mapping] = {
                "url": entry.get("url"),
                "classified_count": entry.get("classifiedCount"),
            }

    return result


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------


def extract_all(url: str) -> Optional[dict[str, Any]]:
    """Fetch a page and extract all available data from it.

    Returns a dict with keys:
      - url
      - place
      - prices (current: kauf + miete)
      - indices (historical yearly + evolution)
      - serp_links (active listings)
      - child_links (for crawling)
    """
    from urllib.parse import urlparse

    html = fetch_page(url)
    if not html:
        logger.error("No HTML to extract from %s", url)
        return None

    root = parse_ufrn_json(html)
    if not root:
        logger.error("Could not parse __UFRN_FETCHER__ from %s", url)
        return None

    # Extract the URL path to find the matching data key
    path = urlparse(url).path
    page_data = extract_page_data(root, path)
    if not page_data:
        return None

    return {
        "url": url,
        "place": extract_place_info(page_data),
        "prices": extract_current_prices(page_data),
        "indices": extract_indices(page_data),
        "serp_links": extract_serp_links(page_data),
        "child_links": extract_place_links(page_data),
    }
