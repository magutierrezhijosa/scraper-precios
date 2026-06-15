# Immowelt Price Scraper

Scrape real estate prices (purchase + rent) from [immowelt.de](https://www.immowelt.de/immobilienpreise) for all German cities.

## Output

| CSV | Description |
|-----|-------------|
| `output/prices_current.csv` | Current €/m² prices by location, transaction type, and property type (house/apartment) |
| `output/prices_history.csv` | Yearly historical prices (10 years) per location |
| `output/prices_by_rooms.csv` | (planned) Price breakdown by room count |
| `output/prices_by_house_type.csv` | (planned) Price breakdown by house type |

## Quick start

```bash
pip install -r requirements.txt
playwright install chromium   # if using Playwright fallback
python -m scraper.main --quick
```

## DataDome Anti-Bot Protection

**Immowelt uses DataDome** — a JS challenge + CAPTCHA system. Automated HTTP clients
(`requests`, `curl_cffi`, even Playwright headless) get blocked by DataDome from
certain IP ranges.

### How the scraper handles it

The fetcher uses **three strategies** in order of preference:

| Strategy | Description | Status |
|----------|-------------|--------|
| `curl_cffi` | TLS fingerprint mimic (chrome124) | Blocked if IP flagged |
| Playwright | Full Chrome with stealth scripts | Blocked if IP flagged |
| **Local cache** | Serve pre-fetched HTML from disk | **Always works** |

When live strategies fail, use the **local cache** approach:

### Cache workflow

1. **Pre-fetch pages** using a method that works (browser, curl from another
   machine, the `webfetch` tool in OpenCode, etc.)
2. Save each page as `cache/<hash>.html` (handled automatically)
3. Run the scraper — it reads from cache instead of fetching live

```bash
# Pre-fetch all state pages
python scripts/prefetch.py

# Or a single URL
python scripts/prefetch.py --url https://www.immowelt.de/immobilienpreise/bayern/ad04de9

# Pre-fetch states + all cities (may take a while)
python scripts/prefetch.py --cities

# Use a custom cache directory
python scripts/prefetch.py --cache-dir my_cache
```

The pre-fetcher tries the live strategies first. If they fail, use a browser
to manually save the HTML into the cache directory, or use OpenCode's
`webfetch` tool to pre-fetch URLs.

## Full crawl

```bash
# Crawl all states and cities
python -m scraper.main

# Use cached pages only (no live requests)
python -m scraper.main --no-cache --cache-dir cache

# Verbose logging to debug fetch issues
python -m scraper.main --verbose
```

## How it works

1. **National page** (`/immobilienpreise/deutschland`): Lists all 16 states
2. **State pages**: Each state lists its cities
3. **City pages**: Each city has current €/m² prices + 10-year history

Data is extracted from `__UFRN_FETCHER__` — a JSON blob embedded in the
server-rendered HTML. No API calls or client-side rendering needed.

The embedded JSON structure has the keys:
- `pricePageContext.place` — location metadata
- `prices.sell / prices.rent` — current price data by property type
- `indices` — yearly historical indices + short-term evolution
- `placeLinkBoxes` — links to child locations (states, cities, neighborhoods)
- `serpLinks` — links to active listings with classified counts

## Project structure

```
scraper/
├── config.py        # URLs, timing, accuracy mapping
├── models.py        # Dataclasses (PriceEntry, HistoricalPrice, etc.)
├── extract.py       # JSON extraction + price/indices/link parsing
├── fetcher.py       # Multi-strategy HTTP client + cache layer
├── crawl.py         # Crawl orchestrator (national → states → cities)
└── main.py          # CLI entry point
scripts/
└── prefetch.py      # Pre-fetch helper for cache population
cache/               # Cached HTML pages (auto-populated)
output/              # Generated CSVs
```
