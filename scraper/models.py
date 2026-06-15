"""Typed dataclasses for Immowelt price data."""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class PriceEntry:
    """Current price data for a specific property type and transaction."""
    location_id: str
    location_name: str
    location_slug: str
    level: str  # country / region / city
    state_name: Optional[str]
    transaction_type: str  # kauf / miete
    property_type: str  # wohnung / haus / hybrid
    avg_price_per_m2: Optional[int] = None
    min_price_per_m2: Optional[int] = None
    max_price_per_m2: Optional[int] = None
    accuracy: Optional[str] = None
    data_date: Optional[str] = None
    scrape_date: str = ""
    url: str = ""
    listings_count: Optional[int] = None


@dataclass
class PriceByRooms:
    """Average price per m² broken down by number of rooms."""
    location_id: str
    transaction_type: str
    rooms: int
    avg_price_per_m2: Optional[int] = None


@dataclass
class PriceByHouseType:
    """Average price per m² broken down by house type."""
    location_id: str
    transaction_type: str
    house_type: str
    avg_price_per_m2: Optional[int] = None


@dataclass
class HistoricalPrice:
    """Yearly historical price data."""
    location_id: str
    transaction_type: str
    property_type: str
    year: int
    avg_price_per_m2: Optional[int] = None
    change_vs_previous_pct: Optional[float] = None


@dataclass
class NearbyPrice:
    """Price data for a nearby/related location."""
    location_id: str
    transaction_type: str
    related_location_id: str
    related_location_name: str
    related_level: str
    avg_price_per_m2: Optional[int] = None
