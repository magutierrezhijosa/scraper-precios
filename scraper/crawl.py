"""Orchestrator that crawls the Immowelt price hierarchy.

Flow:
  1. National page → discover 16 state URLs
  2. Each state page → discover city URLs + state-level prices
  3. Each city → fetch Kaufpreise + Mietpreise pages, extract all data
  4. Write results incrementally to CSVs
"""

import csv
import logging
import os
import time
from typing import Any, Optional
from urllib.parse import urlparse

from scraper.config import (
    NATIONAL_KAUF_URL,
    OUTPUT_DIR,
    REQUEST_DELAY_SECONDS,
    SCRAPE_DATE,
)
from scraper.extract import (
    extract_all,
    extract_place_info,
    extract_current_prices,
    extract_place_links,
    parse_ufrn_json,
    extract_page_data,
)
from scraper.fetcher import fetch_page

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSV writers (append mode, incremental)
# ---------------------------------------------------------------------------

_CSV_FIELDS = {
    "prices_current": [
        "scrape_date", "url", "level", "state_name", "location_name",
        "location_slug", "location_id", "transaction_type", "property_type",
        "avg_price_per_m2", "min_price_per_m2", "max_price_per_m2",
        "accuracy", "data_date", "listings_count",
    ],
    "prices_history": [
        "location_id", "transaction_type", "property_type",
        "year", "avg_price_per_m2", "change_vs_previous_pct",
    ],
}


def _ensure_output_dir() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _write_csv(csv_key: str, row: dict[str, Any]) -> None:
    """Append a single row to *csv_key*.csv, writing header if needed."""
    _ensure_output_dir()
    filename = f"{csv_key}.csv"
    path = os.path.join(OUTPUT_DIR, filename)
    write_header = not os.path.exists(path)

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS[csv_key])
        if write_header:
            writer.writeheader()
        writer.writerow(row)


# ---------------------------------------------------------------------------
# Price flattening helpers
# ---------------------------------------------------------------------------


def _write_current_prices(
    data: dict[str, Any],
    transaction_type: str,
) -> None:
    """Write current price entries to CSV for one transaction type."""
    place = data["place"]
    prices = data["prices"].get(transaction_type, {})
    url = data["url"]
    serp = data.get("serp_links", {})

    for prop_type, prop_key in (
        ("wohnung", "apartment"),
        ("haus", "house"),
    ):
        entry = prices.get(prop_key, {})
        if not entry.get("avg_price") and not entry.get("min_price"):
            continue  # skip empty entries

        # Determine listing count
        if transaction_type == "kauf":
            listings_key = f"kauf_{prop_type}"
        else:
            continue  # SERP links for rent may have different keys

        listings = serp.get(listings_key, {}).get("classified_count") if serp else None

        row = {
            "scrape_date": SCRAPE_DATE,
            "url": url,
            "level": place.get("level", ""),
            "state_name": place.get("state_name", ""),
            "location_name": place.get("name", ""),
            "location_slug": place.get("slug", ""),
            "location_id": place.get("id", ""),
            "transaction_type": transaction_type,
            "property_type": prop_type,
            "avg_price_per_m2": entry.get("avg_price"),
            "min_price_per_m2": entry.get("min_price"),
            "max_price_per_m2": entry.get("max_price"),
            "accuracy": entry.get("accuracy", ""),
            "data_date": entry.get("data_date", ""),
            "listings_count": listings,
        }
        _write_csv("prices_current", row)


def _write_history(
    data: dict[str, Any],
    transaction_type: str,
) -> None:
    """Write historical yearly prices to CSV."""
    place = data["place"]
    location_id = place.get("id", "")
    indices = data.get("indices", {})

    for prop_type in ("apartment", "house"):
        yearly_key = f"{prop_type}_yearly"
        yearly_data = indices.get(yearly_key, [])
        if not yearly_data:
            continue

        property_type = "wohnung" if prop_type == "apartment" else "haus"

        for year_entry in yearly_data:
            row = {
                "location_id": location_id,
                "transaction_type": transaction_type,
                "property_type": property_type,
                "year": year_entry.get("year"),
                "avg_price_per_m2": year_entry.get("avg_price"),
                "change_vs_previous_pct": year_entry.get("change_vs_previous_pct"),
            }
            _write_csv("prices_history", row)


# ---------------------------------------------------------------------------
# Single page process
# ---------------------------------------------------------------------------


def _process_page(url: str, transaction_type: str) -> Optional[dict[str, Any]]:
    """Fetch a single page and extract + persist data. Returns extracted data."""
    logger.info("  Fetching %s (%s)", url, transaction_type)
    data = extract_all(url)
    if not data:
        return None

    # Write current prices
    if data["prices"].get(transaction_type):
        _write_current_prices(data, transaction_type)

    # Write history (only for city-level pages ideally, but we write all)
    _write_history(data, transaction_type)

    return data


# ---------------------------------------------------------------------------
# City processing
# ---------------------------------------------------------------------------


def _process_city(city_url: str) -> None:
    """Process one city: fetch kauf + miete pages."""
    # Kauf
    kauf_url = city_url  # the URL we got is already the kauf URL
    data = _process_page(kauf_url, "kauf")
    if not data:
        logger.warning("  Failed to fetch kauf page: %s", kauf_url)

    time.sleep(REQUEST_DELAY_SECONDS)

    # Miete — derive rent URL by inserting /mietpreise/ after /immobilienpreise/
    # e.g., /immobilienpreise/berlin/berlin-10115/ad08de8634
    #    → /immobilienpreise/mietpreise/berlin/berlin-10115/ad08de8634
    if "/immobilienpreise/" in kauf_url and "/mietpreise/" not in kauf_url:
        miete_url = kauf_url.replace(
            "/immobilienpreise/", "/immobilienpreise/mietpreise/", 1,
        )
    else:
        miete_url = kauf_url  # fallback

    _process_page(miete_url, "miete")
    time.sleep(REQUEST_DELAY_SECONDS)


# ---------------------------------------------------------------------------
# State processing
# ---------------------------------------------------------------------------


def _process_state_page(state_url: str) -> Optional[dict[str, Any]]:
    """Fetch a state page and extract data using the new JSON API."""
    html = fetch_page(state_url)
    if not html:
        return None

    root = parse_ufrn_json(html)
    if not root:
        return None

    path = urlparse(state_url).path
    page_data = extract_page_data(root, path)
    if not page_data:
        return None

    return {
        "url": state_url,
        "place": extract_place_info(page_data),
        "prices": extract_current_prices(page_data),
        "indices": {},
        "serp_links": {},
        "child_links": extract_place_links(page_data),
    }


def _process_state(state_url: str) -> list[str]:
    """Process one state: extract state-level prices, return city URLs."""
    logger.info("Processing state: %s", state_url)

    state_data = _process_state_page(state_url)
    if not state_data:
        return []

    # Write state-level prices
    if state_data["prices"].get("kauf"):
        _write_current_prices(state_data, "kauf")

    # Discover city URLs from placeLinkBoxes
    city_urls = []
    seen = set()
    for link in state_data["child_links"]:
        if link["place_type"] == "city" and link["url"] not in seen:
            seen.add(link["url"])
            city_urls.append(link["url"])

    logger.info("  Found %d cities in state", len(city_urls))
    return city_urls


# ---------------------------------------------------------------------------
# Main crawl orchestrator
# ---------------------------------------------------------------------------


def crawl_all() -> dict[str, int]:
    """Run the full crawl. Returns stats dict."""
    stats: dict[str, int] = {"states": 0, "cities": 0, "errors": 0}

    logger.info("=== Starting Immowelt price crawl ===")
    logger.info("National page: %s", NATIONAL_KAUF_URL)

    # 1. Fetch national page → discover states
    national_data = _process_state_page(NATIONAL_KAUF_URL)
    if not national_data:
        logger.error("Failed to process national page!")
        return stats

    # Collect state URLs
    state_urls = []
    seen = set()
    for link in national_data["child_links"]:
        if link["place_type"] == "region" and link["url"] not in seen:
            seen.add(link["url"])
            state_urls.append(link["url"])

    logger.info("Found %d states", len(state_urls))

    # 2. Process each state
    for state_url in state_urls:
        stats["states"] += 1
        try:
            city_urls = _process_state(state_url)
        except Exception as exc:
            logger.error("Error processing state %s: %s", state_url, exc)
            stats["errors"] += 1
            continue

        time.sleep(REQUEST_DELAY_SECONDS)

        # 3. Process each city in this state
        for city_url in city_urls:
            stats["cities"] += 1
            try:
                _process_city(city_url)
            except Exception as exc:
                logger.error("Error processing city %s: %s", city_url, exc)
                stats["errors"] += 1
                continue

            time.sleep(REQUEST_DELAY_SECONDS)

    logger.info(
        "=== Crawl complete: %d states, %d cities, %d errors ===",
        stats["states"], stats["cities"], stats["errors"],
    )
    return stats
