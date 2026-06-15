#!/usr/bin/env python3
"""Immowelt price scraper — entry point.

Usage:
    python -m scraper.main            # full crawl
    python -m scraper.main --quick    # quick test (national + 1 state + 1 city)
"""

import argparse
import logging
import sys

from scraper.config import CACHE_DIR, NATIONAL_KAUF_URL
from scraper.crawl import crawl_all, _process_state, _process_city
from scraper.extract import parse_ufrn_json, extract_page_data, extract_place_links, extract_place_info
from scraper.fetcher import fetch_page, close_browser


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def quick_test(cache_dir: str, no_cache: bool) -> None:
    """Quick test: national -> first state -> first city."""
    import os
    from urllib.parse import urlparse

    logging.info("=== Quick test ===")
    if cache_dir:
        logging.info("Cache directory: %s", cache_dir)

    html = fetch_page(NATIONAL_KAUF_URL, use_cache=not no_cache)
    if not html:
        logging.error("Failed to fetch national page")
        return

    root = parse_ufrn_json(html)
    if not root:
        logging.error("Failed to parse JSON from national page")
        return

    path = urlparse(NATIONAL_KAUF_URL).path
    page_data = extract_page_data(root, path)
    if not page_data:
        return

    place = extract_place_info(page_data)
    logging.info("National page: %s (%s)", place["name"], place["level"])

    links = extract_place_links(page_data)
    state_urls = [l["url"] for l in links if l["place_type"] == "region"]
    if not state_urls:
        logging.error("No state URLs found")
        return

    first_state = state_urls[0]
    logging.info("Testing with first state: %s", first_state)

    city_urls = _process_state(first_state)
    if city_urls:
        first_city = city_urls[0]
        logging.info("Testing with first city: %s", first_city)
        _process_city(first_city)

    logging.info("=== Quick test complete ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="Immowelt price scraper")
    parser.add_argument(
        "--quick", action="store_true",
        help="Run a quick test (national + 1 state + 1 city)",
    )
    parser.add_argument(
        "--cache-dir", default=CACHE_DIR,
        help=f"Directory for cached HTML pages (default: {CACHE_DIR})",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Skip local cache and force live fetch",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Verbose logging (DEBUG level)",
    )
    args = parser.parse_args()

    # Override cache dir in config
    if args.cache_dir:
        import scraper.config as cfg
        cfg.CACHE_DIR = args.cache_dir

    setup_logging(verbose=args.verbose)

    try:
        if args.quick:
            quick_test(args.cache_dir, args.no_cache)
        else:
            stats = crawl_all()
            logging.info(
                "Done. States: %d, Cities: %d, Errors: %d",
                stats["states"], stats["cities"], stats["errors"],
            )
    finally:
        close_browser()


if __name__ == "__main__":
    main()
