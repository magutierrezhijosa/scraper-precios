#!/usr/bin/env python3
"""Pre-fetch Immowelt pages to cache, bypassing DataDome.

This script discovers all URLs in the crawl hierarchy and attempts to
fetch each page.  It saves successful results to the cache directory so
the main scraper can process them offline.

Phases:
  1. Fetch national page → discover 16 state URLs
  2. Fetch each state page → discover city URLs
  3. Optionally fetch each city (kauf + miete)

Usage:
    python scripts/prefetch.py                              # states only
    python scripts/prefetch.py --cities                     # states + all cities
    python scripts/prefetch.py --url https://...            # single URL
    python scripts/prefetch.py --cache-dir my_cache         # custom cache dir
"""

import argparse
import logging
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from urllib.parse import urlparse

import scraper.config as cfg
from scraper.fetcher import fetch_page, close_browser, _write_cache, _read_cache
from scraper.extract import parse_ufrn_json, extract_page_data, extract_place_links, extract_place_info

logger = logging.getLogger("prefetch")


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def fetch_and_cache(url: str, no_cache: bool = False) -> bool:
    """Fetch a URL and save to cache. Returns True on success."""
    # Skip if already cached
    if not no_cache and _read_cache(url) is not None:
        logger.info("  [CACHED] %s", url)
        return True

    # Try to fetch
    logger.info("  Fetching %s", url)
    html = fetch_page(url, use_cache=False)
    if html:
        logger.debug("  OK (%d bytes)", len(html))
        return True
    else:
        logger.warning("  FAILED %s", url)
        return False


def discover_urls(national_url: str) -> tuple[list[str], list[str]]:
    """Fetch the national page and return (state_urls, city_urls)."""
    logger.info("=== Phase 0: National page ===")
    if not fetch_and_cache(national_url):
        logger.error("Cannot fetch national page. Aborting.")
        return [], []

    # Parse it
    from scraper.fetcher import _read_cache
    html = _read_cache(national_url)
    root = parse_ufrn_json(html)
    path = urlparse(national_url).path
    page_data = extract_page_data(root, path)

    links = extract_place_links(page_data)
    states = [l["url"] for l in links if l["place_type"] == "region"]
    cities = [l["url"] for l in links if l["place_type"] == "city"]
    logger.info("Found %d states, %d top cities", len(states), len(cities))
    return states, cities


def discover_cities(state_url: str) -> list[str]:
    """Fetch a state page and return city URLs."""
    name = state_url.rstrip("/").split("/")[-1]
    logger.info("  === State: %s ===", name)
    if not fetch_and_cache(state_url):
        return []

    from scraper.fetcher import _read_cache
    html = _read_cache(state_url)
    root = parse_ufrn_json(html)
    path = urlparse(state_url).path
    page_data = extract_page_data(root, path)

    links = extract_place_links(page_data)
    cities = [l["url"] for l in links if l["place_type"] == "city"]
    logger.info("    Found %d cities", len(cities))
    return cities


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-fetch Immowelt pages")
    parser.add_argument("--cities", action="store_true", help="Also fetch all city pages")
    parser.add_argument("--url", help="Fetch a single URL only")
    parser.add_argument("--cache-dir", default=cfg.CACHE_DIR, help="Cache directory")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    if args.cache_dir:
        cfg.CACHE_DIR = args.cache_dir

    setup_logging(args.verbose)
    os.makedirs(cfg.CACHE_DIR, exist_ok=True)

    total_ok = 0
    total_fail = 0

    try:
        if args.url:
            ok = fetch_and_cache(args.url, no_cache=True)
            total_ok += 1 if ok else 0
            total_fail += 0 if ok else 1
            logger.info("Result: %s", "OK" if ok else "FAILED")
        else:
            # Phase 0: National
            state_urls, top_cities = discover_urls(cfg.NATIONAL_KAUF_URL)
            total_ok += 1
            time.sleep(cfg.REQUEST_DELAY_SECONDS)

            # Phase 1: States
            all_cities = list(top_cities)
            logger.info("\n=== Phase 1: %d States ===", len(state_urls))
            for i, url in enumerate(state_urls, 1):
                cities = discover_cities(url)
                all_cities.extend(cities)
                total_ok += 1
                time.sleep(cfg.REQUEST_DELAY_SECONDS)

            # Phase 2: Cities
            if args.cities:
                city_only = [c for c in all_cities if c not in top_cities]
                logger.info("\n=== Phase 2: %d Cities ===", len(city_only))
                for i, url in enumerate(city_only, 1):
                    ok = fetch_and_cache(url, no_cache=True)
                    if ok:
                        total_ok += 1
                    else:
                        total_fail += 1
                    time.sleep(cfg.REQUEST_DELAY_SECONDS)

                    # Also fetch rent version
                    if "/immobilienpreise/" in url and "/mietpreise/" not in url:
                        rent_url = url.replace(
                            "/immobilienpreise/", "/immobilienpreise/mietpreise/", 1
                        )
                        ok = fetch_and_cache(rent_url, no_cache=True)
                        if ok:
                            total_ok += 1
                        else:
                            total_fail += 1
                        time.sleep(cfg.REQUEST_DELAY_SECONDS)

        logger.info(
            "\n=== Done: %d OK, %d FAILED ===", total_ok, total_fail
        )

    finally:
        close_browser()


if __name__ == "__main__":
    main()
