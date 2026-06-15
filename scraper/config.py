"""Configuration for the Immowelt scraper."""

from datetime import date, datetime

# Base URLs
BASE_URL = "https://www.immowelt.de"
NATIONAL_KAUF_URL = f"{BASE_URL}/immobilienpreise/deutschland"
NATIONAL_MIETE_URL = f"{BASE_URL}/immobilienpreise/mietpreise/deutschland"

# Request headers to mimic a real browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Politeness delay between requests (seconds)
REQUEST_DELAY_SECONDS = 1.5

# Request timeout
REQUEST_TIMEOUT = 30

# Max retries per request
MAX_RETRIES = 3

# Output directory
OUTPUT_DIR = "output"

# Cache directory for pre-fetched HTML pages (to bypass DataDome)
# User can populate this by fetching pages manually (browser, webfetch, etc.)
CACHE_DIR = "cache"

# Date of this scrape
SCRAPE_DATE = date.today().isoformat()

# Accuracy mapping
ACCURACY_MAP = {
    5: "Hohe Genauigkeit",
    4: "Gute Genauigkeit",
    3: "Mittelmäßige Genauigkeit",
    2: "Niedrige Genauigkeit",
    1: "Sehr niedrige Genauigkeit",
    0: "Unbekannt",
}
