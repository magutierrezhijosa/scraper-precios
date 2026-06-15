"""Page fetcher with local cache support and multi-strategy bypass.

Cache-first: if CACHE_DIR has a file for the URL, serve it.
Live fallback: curl_cffi → Playwright.
"""

import hashlib
import logging
import os
import re
import time
from typing import Optional

from scraper.config import CACHE_DIR, REQUEST_DELAY_SECONDS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

# Try curl_cffi for TLS fingerprint mimicry
try:
    from curl_cffi import requests as curl_requests

    CURL_AVAILABLE = True
except ImportError:
    CURL_AVAILABLE = False
    logger.info("curl_cffi not available, falling back to requests")

# Try Playwright for full browser emulation
try:
    from playwright.sync_api import sync_playwright, Browser, Page

    PW_AVAILABLE = True
except ImportError:
    PW_AVAILABLE = False
    logger.info("playwright not available")


# ---------------------------------------------------------------------------
# Local cache (directory-based: urls are hashed)
# ---------------------------------------------------------------------------


def _cache_path(url: str) -> str:
    """Return the cache file path for a URL."""
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"{h}.html")


def _read_cache(url: str) -> Optional[str]:
    """Read cached HTML for *url*. Returns None on miss."""
    path = _cache_path(url)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if "__UFRN_FETCHER__" in content:
            logger.debug("Cache HIT for %s", url)
            return content
        logger.debug("Cache MISS (no data marker) for %s", url)
        return None
    except Exception as exc:
        logger.debug("Cache read error for %s: %s", url, exc)
        return None


def _write_cache(url: str, html: str) -> None:
    """Write HTML to the cache directory."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(url)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.debug("Cached %s", url)
    except Exception as exc:
        logger.warning("Failed to cache %s: %s", url, exc)


# ---------------------------------------------------------------------------
# Curl-CFFI strategy (fast, TLS fingerprint mimic)
# ---------------------------------------------------------------------------

_curl_session = None


def _get_curl_session():
    global _curl_session
    if _curl_session is None and CURL_AVAILABLE:
        _curl_session = curl_requests.Session()
    return _curl_session


def _fetch_curl(url: str) -> Optional[str]:
    """Try fetching with curl_cffi (mimics real browser TLS)."""
    if not CURL_AVAILABLE:
        return None
    try:
        s = _get_curl_session()
        resp = s.get(
            url,
            impersonate="chrome124",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            },
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200 and "__UFRN_FETCHER__" in resp.text:
            return resp.text
        logger.debug(
            "curl_cffi got status %d, len=%d, has_data=%s",
            resp.status_code, len(resp.text), "__UFRN_FETCHER__" in resp.text,
        )
        return None
    except Exception as exc:
        logger.debug("curl_cffi failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Playwright strategy (full browser, handles JS challenges)
# ---------------------------------------------------------------------------

_pw_browser: Optional[Browser] = None
_pw_page = None


def _get_pw():
    """Lazy-init shared Playwright browser+page."""
    global _pw_browser, _pw_page
    if _pw_page is None and PW_AVAILABLE:
        playwright = sync_playwright().start()
        _pw_browser = playwright.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = _pw_browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="de-DE",
            viewport={"width": 1920, "height": 1080},
        )
        # Stealth injections
        context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            window.chrome = {runtime: {}};
        """
        )
        _pw_page = context.new_page()
    return _pw_page


def _fetch_playwright(url: str) -> Optional[str]:
    """Try fetching with Playwright (real browser)."""
    if not PW_AVAILABLE:
        return None
    try:
        page = _get_pw()
        page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
        # Wait for data to load (DataDome may challenge then resolve)
        time.sleep(5)
        html = page.content()
        if "__UFRN_FETCHER__" in html:
            return html
        logger.debug("Playwright: no UFRN_FETCHER, page title=%s", page.title())
        return None
    except Exception as exc:
        logger.debug("Playwright failed: %s", exc)
        return None


def close_browser():
    """Cleanup Playwright browser."""
    global _pw_browser, _pw_page
    if _pw_browser:
        try:
            _pw_browser.close()
        except Exception:
            pass
        _pw_browser = None
        _pw_page = None


# ---------------------------------------------------------------------------
# Public fetch_page with cache + multi-strategy fallback
# ---------------------------------------------------------------------------


def fetch_page(url: str, use_cache: bool = True) -> Optional[str]:
    """Fetch a page — cache first, then live strategies.

    Args:
        url: The URL to fetch.
        use_cache: If True (default), check the local cache before live fetch.
                   Live results are ALWAYS written to cache on success.

    Returns:
        HTML string, or None if all strategies fail.
    """
    # Strategy 0: local cache
    if use_cache:
        cached = _read_cache(url)
        if cached is not None:
            return cached

    # Strategy 1: curl_cffi (fastest)
    html = _fetch_curl(url)
    if html:
        _write_cache(url, html)
        return html

    # Strategy 2: Playwright (real browser)
    html = _fetch_playwright(url)
    if html:
        _write_cache(url, html)
        return html

    logger.error("All fetch strategies failed for %s", url)
    return None
