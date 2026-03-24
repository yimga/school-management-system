"""
GeoIP and regional helpers without ORM (tables removed in siteconfig 0075).

Lookup path: Django cache key ``geoip:{ip}`` (dict shaped like a GeoIP row).
Region defaults are static until a future registry / edge integration owns them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Dict, List, Optional

from django.core.cache import cache
from django.utils import timezone


@dataclass(frozen=True)
class RegionalConfigSnapshot:
    """Read-only regional defaults (replaces deleted RegionalConfig model)."""

    region: str
    currency: str
    language: str
    timezone: str


# Default economics/locale per macro-region (platform fallback; not tenant-specific).
REGION_DEFAULTS: Dict[str, RegionalConfigSnapshot] = {
    "WEST_AFRICA": RegionalConfigSnapshot(
        "WEST_AFRICA", "NGN", "en", "Africa/Lagos"
    ),
    "EAST_AFRICA": RegionalConfigSnapshot(
        "EAST_AFRICA", "KES", "en", "Africa/Nairobi"
    ),
    "SOUTHERN_AFRICA": RegionalConfigSnapshot(
        "SOUTHERN_AFRICA", "ZAR", "en", "Africa/Johannesburg"
    ),
    "CENTRAL_AFRICA": RegionalConfigSnapshot(
        "CENTRAL_AFRICA", "XAF", "fr", "Africa/Douala"
    ),
    "NORTH_AFRICA": RegionalConfigSnapshot(
        "NORTH_AFRICA", "EGP", "ar", "Africa/Cairo"
    ),
}

# ISO 3166-1 alpha-2 → macro-region (subset; expand in registries when productized).
_COUNTRY_TO_REGION: Dict[str, str] = {
    "NG": "WEST_AFRICA",
    "GH": "WEST_AFRICA",
    "SL": "WEST_AFRICA",
    "GM": "WEST_AFRICA",
    "CV": "WEST_AFRICA",
    "KE": "EAST_AFRICA",
    "UG": "EAST_AFRICA",
    "TZ": "EAST_AFRICA",
    "RW": "EAST_AFRICA",
    "BI": "EAST_AFRICA",
    "ZA": "SOUTHERN_AFRICA",
    "BW": "SOUTHERN_AFRICA",
    "ZW": "SOUTHERN_AFRICA",
    "NA": "SOUTHERN_AFRICA",
    "LS": "SOUTHERN_AFRICA",
    "CM": "CENTRAL_AFRICA",
    "CF": "CENTRAL_AFRICA",
    "CD": "CENTRAL_AFRICA",
    "AO": "CENTRAL_AFRICA",
    "EG": "NORTH_AFRICA",
    "TN": "NORTH_AFRICA",
    "DZ": "NORTH_AFRICA",
    "MA": "NORTH_AFRICA",
    "LY": "NORTH_AFRICA",
}


class GeoIPService:
    """GeoIP-style lookups: cache-backed dict only; no database tables."""

    MAXMIND_DB_PATH = "geoip/GeoLite2-City.mmdb"
    CACHE_TIMEOUT = 86400  # 24 hours

    @staticmethod
    def lookup_ip(ip_address: str) -> Optional[Dict[str, Any]]:
        """Return cached geo dict for IP, or None (no ORM / no bundled MaxMind in this path)."""
        cache_key = f"geoip:{ip_address}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        return None

    @staticmethod
    def get_user_region(ip_address: str) -> Optional[str]:
        location = GeoIPService.lookup_ip(ip_address)
        if not location:
            return None
        country_code = (location.get("country_code") or "").upper()
        if not country_code:
            return None
        return _COUNTRY_TO_REGION.get(country_code)

    @staticmethod
    def is_ip_whitelisted(ip_address: str) -> bool:
        """No persistent whitelist store after 0075; always False unless you set cache elsewhere."""
        return False

    @staticmethod
    def check_region_access(region: str, user_group: str) -> bool:
        """No regional access policy store; deny closed until a governance surface exists."""
        return False

    @staticmethod
    def get_region_config(region: Optional[str]) -> Optional[RegionalConfigSnapshot]:
        if not region:
            return None
        return REGION_DEFAULTS.get(region)

    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance in km."""
        r_earth = 6371.0
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return r_earth * c


class LocationBasedAccessControl:
    """Lightweight access hints from cached geo dict only."""

    def __init__(self, ip_address: str):
        self.ip_address = ip_address
        self.location = GeoIPService.lookup_ip(ip_address)
        self.region = GeoIPService.get_user_region(ip_address)

    def is_allowed(self, required_region: Optional[str] = None) -> bool:
        if not self.location:
            return False
        if GeoIPService.is_ip_whitelisted(self.ip_address):
            return True
        if self.location.get("is_vpn") or self.location.get("is_proxy"):
            return False
        if required_region and self.region != required_region:
            return False
        return True

    def get_access_level(self) -> str:
        if not self.location:
            return "denied"
        if GeoIPService.is_ip_whitelisted(self.ip_address):
            return "full"
        if self.location.get("is_vpn"):
            return "restricted"
        return "full"

    def enforce_data_residency(self, data_region: str) -> bool:
        if not self.region:
            return False
        config = GeoIPService.get_region_config(self.region)
        if not config:
            return False
        return config.region == data_region


class RegionalDataLocalization:
    """Regional formatting; currency symbols via siteconfig.currency."""

    REGIONAL_CURRENCIES = {
        "WEST_AFRICA": {"NGN", "GHS", "SLL", "GMD", "CVE"},
        "EAST_AFRICA": {"KES", "UGX", "TZS", "RWF", "BIF"},
        "SOUTHERN_AFRICA": {"ZAR", "BWP", "ZWL", "NAD", "LSL"},
        "CENTRAL_AFRICA": {"XAF", "XOF", "CDF", "AOA"},
        "NORTH_AFRICA": {"EGP", "TND", "DZD", "MAD", "LYD"},
    }

    REGIONAL_LANGUAGES = {
        "WEST_AFRICA": ["en", "fr", "ha", "yo"],
        "EAST_AFRICA": ["en", "sw", "am"],
        "SOUTHERN_AFRICA": ["en", "zu", "xh", "st"],
        "CENTRAL_AFRICA": ["fr", "en", "lin"],
        "NORTH_AFRICA": ["ar", "fr", "en"],
    }

    @staticmethod
    def get_regional_currency(region: Optional[str]) -> str:
        config = GeoIPService.get_region_config(region or "")
        return config.currency if config else "USD"

    @staticmethod
    def get_regional_languages(region: Optional[str]) -> List[str]:
        if not region:
            return ["en"]
        return RegionalDataLocalization.REGIONAL_LANGUAGES.get(region, ["en"])

    @staticmethod
    def get_regional_timezone(region: Optional[str]) -> str:
        config = GeoIPService.get_region_config(region or "")
        return config.timezone if config else "UTC"

    @staticmethod
    def format_currency(amount: float, region: str, decimal_places: int = 2) -> str:
        from apps.siteconfig.currency import get_currency_symbol

        currency = RegionalDataLocalization.get_regional_currency(region)
        symbol = get_currency_symbol(currency)
        formatted_amount = f"{amount:,.{decimal_places}f}"
        return f"{symbol}{formatted_amount}"

    @staticmethod
    def apply_regional_rules(user_id: int, ip_address: str) -> Dict[str, Any]:
        region = GeoIPService.get_user_region(ip_address)
        return {
            "region": region,
            "currency": RegionalDataLocalization.get_regional_currency(region),
            "languages": RegionalDataLocalization.get_regional_languages(region),
            "timezone": RegionalDataLocalization.get_regional_timezone(region),
        }


class GeoIPEventLogger:
    """Structured geo events in cache (short TTL), not SQL."""

    @staticmethod
    def log_access(ip_address: str, user_id: int, resource: str, allowed: bool) -> None:
        location = GeoIPService.lookup_ip(ip_address)
        if not location:
            return
        event = {
            "timestamp": timezone.now().isoformat(),
            "ip": ip_address,
            "user": user_id,
            "resource": resource,
            "allowed": allowed,
            "country": location.get("country_code"),
            "city": location.get("city"),
        }
        cache.set(
            f"geo_event:{ip_address}:{user_id}:{resource}",
            event,
            86400,
        )

    @staticmethod
    def get_access_summary(days: int = 30) -> Dict[str, Any]:
        _ = timezone.now() - timedelta(days=days)
        return {
            "period_days": days,
            "total_access_attempts": 0,
            "allowed": 0,
            "denied": 0,
            "vpn_detected": 0,
        }
