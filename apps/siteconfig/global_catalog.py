"""
Global country/city/timezone catalog utilities for provisioning and tenant setup.

Phase 1 foundation:
- Country list from ISO metadata (pycountry)
- City catalog from geonamescache (global city index)
- Timezone list from pytz
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pytz

try:
    import pycountry
except Exception:  # pragma: no cover - fallback path
    pycountry = None

try:
    import geonamescache
except Exception:  # pragma: no cover - fallback path
    geonamescache = None


# Pragmatic defaults for common deployments. Unknown countries fall back to USD/en.
_CURRENCY_BY_COUNTRY = {
    "CMR": "XAF",
    "NGA": "NGN",
    "KEN": "KES",
    "UGA": "UGX",
    "TZA": "TZS",
    "RWA": "RWF",
    "GHA": "GHS",
    "ZAF": "ZAR",
    "USA": "USD",
    "CAN": "CAD",
    "GBR": "GBP",
    "FRA": "EUR",
    "DEU": "EUR",
    "ESP": "EUR",
    "ITA": "EUR",
    "IND": "INR",
    "CHN": "CNY",
    "JPN": "JPY",
    "BRA": "BRL",
    "MEX": "MXN",
    "AUS": "AUD",
}

_LANGUAGE_BY_COUNTRY = {
    "FRA": "fr",
    "CMR": "en",
    "NGA": "en",
    "KEN": "sw",
    "UGA": "en",
    "GBR": "en",
    "USA": "en",
}

_ALPHA2_TO_ALPHA3_FALLBACK = {
    "CM": "CMR",
    "UG": "UGA",
    "NG": "NGA",
    "KE": "KEN",
    "TZ": "TZA",
    "RW": "RWA",
    "GH": "GHA",
    "ZA": "ZAF",
    "US": "USA",
    "CA": "CAN",
    "GB": "GBR",
    "FR": "FRA",
    "DE": "DEU",
    "ES": "ESP",
    "IT": "ITA",
    "IN": "IND",
    "CN": "CHN",
    "JP": "JPN",
    "BR": "BRA",
    "MX": "MEX",
    "AU": "AUS",
}
_ALPHA3_TO_ALPHA2_FALLBACK = {v: k for k, v in _ALPHA2_TO_ALPHA3_FALLBACK.items()}

_FALLBACK_CITIES: list[dict[str, Any]] = [
    {"id": "CMR_DOUALA", "country_code": "CMR", "country_code_alpha2": "CM", "city": "Douala", "timezone": "Africa/Douala", "latitude": 4.0483, "longitude": 9.7043, "population": 3768000},
    {"id": "CMR_YAOUNDE", "country_code": "CMR", "country_code_alpha2": "CM", "city": "Yaounde", "timezone": "Africa/Douala", "latitude": 3.848, "longitude": 11.5021, "population": 4300000},
    {"id": "UGA_KAMPALA", "country_code": "UGA", "country_code_alpha2": "UG", "city": "Kampala", "timezone": "Africa/Kampala", "latitude": 0.3476, "longitude": 32.5825, "population": 1681000},
    {"id": "NGA_LAGOS", "country_code": "NGA", "country_code_alpha2": "NG", "city": "Lagos", "timezone": "Africa/Lagos", "latitude": 6.5244, "longitude": 3.3792, "population": 15000000},
    {"id": "KEN_NAIROBI", "country_code": "KEN", "country_code_alpha2": "KE", "city": "Nairobi", "timezone": "Africa/Nairobi", "latitude": -1.2921, "longitude": 36.8219, "population": 4397000},
    {"id": "GBR_LONDON", "country_code": "GBR", "country_code_alpha2": "GB", "city": "London", "timezone": "Europe/London", "latitude": 51.5072, "longitude": -0.1276, "population": 9648000},
    {"id": "FRA_PARIS", "country_code": "FRA", "country_code_alpha2": "FR", "city": "Paris", "timezone": "Europe/Paris", "latitude": 48.8566, "longitude": 2.3522, "population": 11020000},
    {"id": "USA_NEW_YORK", "country_code": "USA", "country_code_alpha2": "US", "city": "New York", "timezone": "America/New_York", "latitude": 40.7128, "longitude": -74.006, "population": 18800000},
    {"id": "USA_LOS_ANGELES", "country_code": "USA", "country_code_alpha2": "US", "city": "Los Angeles", "timezone": "America/Los_Angeles", "latitude": 34.0522, "longitude": -118.2437, "population": 12400000},
    {"id": "JPN_TOKYO", "country_code": "JPN", "country_code_alpha2": "JP", "city": "Tokyo", "timezone": "Asia/Tokyo", "latitude": 35.6762, "longitude": 139.6503, "population": 37115000},
]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class GlobalGeoCatalog:
    """Read-only global catalog with in-process caching."""

    @classmethod
    def is_available(cls) -> bool:
        return bool(pycountry and geonamescache)

    @classmethod
    def normalize_country_code(cls, code: str | None) -> str:
        """
        Normalize country code to ISO alpha-3 when possible.
        Accepts alpha-2 or alpha-3; returns uppercase input if unknown.
        """
        raw = (code or "").strip().upper()
        if not raw:
            return ""
        if len(raw) == 3:
            if pycountry:
                match = pycountry.countries.get(alpha_3=raw)
                return match.alpha_3 if match else raw
            return raw
        if len(raw) == 2 and pycountry:
            match = pycountry.countries.get(alpha_2=raw)
            if match:
                return match.alpha_3
        if len(raw) == 2:
            return _ALPHA2_TO_ALPHA3_FALLBACK.get(raw, raw)
        return raw

    @classmethod
    def alpha2_for_country(cls, code: str | None) -> str:
        raw = (code or "").strip().upper()
        if not raw:
            return ""
        if len(raw) == 2:
            return raw
        if len(raw) == 3 and pycountry:
            match = pycountry.countries.get(alpha_3=raw)
            if match:
                return match.alpha_2
        if len(raw) == 3:
            return _ALPHA3_TO_ALPHA2_FALLBACK.get(raw, "")
        return ""

    @classmethod
    @lru_cache(maxsize=1)
    def _build_city_indexes(cls) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]], dict[str, str]]:
        country_index: dict[str, list[dict[str, Any]]] = {}
        by_id: dict[str, dict[str, Any]] = {}
        dominant_timezone: dict[str, tuple[str, int]] = {}

        def _add_city(row: dict[str, Any]) -> None:
            alpha3 = cls.normalize_country_code(row.get("country_code"))
            alpha2 = str(row.get("country_code_alpha2") or cls.alpha2_for_country(alpha3)).upper()
            if not alpha3:
                return
            city_id = str(row.get("id") or "")
            if not city_id:
                return
            population = _safe_int(row.get("population"), default=0)
            city = str(row.get("city") or "").strip()
            timezone_name = str(row.get("timezone") or "").strip() or "UTC"
            country_name = ""
            if pycountry and alpha2:
                country = pycountry.countries.get(alpha_2=alpha2)
                if country:
                    country_name = str(getattr(country, "name", "")).strip()
            label = f"{city}, {country_name}" if country_name else city
            payload = {
                "id": city_id,
                "country_code": alpha3,
                "country_code_alpha2": alpha2,
                "city": city,
                "label": label,
                "timezone": timezone_name,
                "latitude": float(row.get("latitude") or 0.0),
                "longitude": float(row.get("longitude") or 0.0),
                "population": population,
            }
            country_index.setdefault(alpha3, []).append(payload)
            by_id[city_id] = payload
            previous = dominant_timezone.get(alpha3)
            if timezone_name and (previous is None or population > previous[1]):
                dominant_timezone[alpha3] = (timezone_name, population)

        if not geonamescache:
            for row in _FALLBACK_CITIES:
                _add_city(row)
            timezone_map = {code: value[0] for code, value in dominant_timezone.items()}
            return country_index, by_id, timezone_map

        gc = geonamescache.GeonamesCache()
        for key, payload in gc.get_cities().items():
            alpha2 = str(payload.get("countrycode") or "").upper()
            alpha3 = cls.normalize_country_code(alpha2)
            if not alpha3:
                continue
            city_id = str(payload.get("geonameid") or key)
            population = _safe_int(payload.get("population"), default=0)
            city = str(payload.get("name") or payload.get("asciiname") or "").strip()
            timezone_name = str(payload.get("timezone") or "").strip() or "UTC"

            _add_city(
                {
                    "id": city_id,
                    "country_code": alpha3,
                    "country_code_alpha2": alpha2,
                    "city": city,
                    "timezone": timezone_name,
                    "latitude": float(payload.get("latitude") or 0.0),
                    "longitude": float(payload.get("longitude") or 0.0),
                    "population": population,
                }
            )

        for code, rows in country_index.items():
            rows.sort(key=lambda item: (-int(item.get("population") or 0), str(item.get("city") or "").lower()))
            country_index[code] = rows

        timezone_map = {code: value[0] for code, value in dominant_timezone.items()}
        return country_index, by_id, timezone_map

    @classmethod
    @lru_cache(maxsize=1)
    def list_countries(cls) -> list[dict[str, str]]:
        """
        Return all countries as [{code, code_alpha2, name, timezone}].
        Falls back to RegionConfig when optional catalog deps are unavailable.
        """
        if not pycountry:
            from apps.siteconfig.models import RegionConfig

            rows = (
                RegionConfig.objects.all()
                .order_by("name")
                .values_list("code", "name", "timezone")
            )
            return [
                {
                    "code": str(code or "").upper(),
                    "code_alpha2": cls.alpha2_for_country(code),
                    "name": str(name or code or "").strip(),
                    "timezone": str(tz or "UTC").strip() or "UTC",
                }
                for code, name, tz in rows
            ]

        _, _, timezone_map = cls._build_city_indexes()
        countries = []
        for item in pycountry.countries:
            alpha3 = str(getattr(item, "alpha_3", "")).upper()
            alpha2 = str(getattr(item, "alpha_2", "")).upper()
            countries.append(
                {
                    "code": alpha3,
                    "code_alpha2": alpha2,
                    "name": str(getattr(item, "name", alpha3)),
                    "timezone": timezone_map.get(alpha3, "UTC"),
                }
            )
        countries.sort(key=lambda row: row["name"])
        return countries

    @classmethod
    def country_name(cls, country_code: str | None) -> str:
        code = cls.normalize_country_code(country_code)
        if not code:
            return ""
        for row in cls.list_countries():
            if row["code"] == code:
                return row["name"]
        return code

    @classmethod
    def country_defaults(cls, country_code: str | None) -> dict[str, str]:
        code = cls.normalize_country_code(country_code)
        if not code:
            return {
                "country_code": "",
                "country_name": "",
                "timezone": "UTC",
                "currency": "USD",
                "default_language": "en",
            }
        country_row = next((row for row in cls.list_countries() if row["code"] == code), None) or {}
        return {
            "country_code": code,
            "country_name": str(country_row.get("name") or code),
            "timezone": str(country_row.get("timezone") or "UTC"),
            "currency": _CURRENCY_BY_COUNTRY.get(code, "USD"),
            "default_language": _LANGUAGE_BY_COUNTRY.get(code, "en"),
        }

    @classmethod
    def get_city(cls, city_id: str | None, country_code: str | None = None) -> dict[str, Any] | None:
        value = (city_id or "").strip()
        if not value:
            return None
        _, by_id, _ = cls._build_city_indexes()
        row = by_id.get(value)
        if not row:
            return None
        requested_country = cls.normalize_country_code(country_code)
        if requested_country and row.get("country_code") != requested_country:
            return None
        return dict(row)

    @classmethod
    def search_cities(
        cls,
        *,
        country_code: str | None = None,
        query: str = "",
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        """
        Search global city catalog by country and optional query.
        Returns ranked results with timezone and coordinates.
        """
        country = cls.normalize_country_code(country_code)
        query_text = (query or "").strip().lower()
        cap = max(1, min(int(limit or 120), 500))
        country_index, _, _ = cls._build_city_indexes()

        if country:
            base_rows = country_index.get(country, [])
        elif query_text:
            # Global text search only when query is present.
            base_rows = []
            for rows in country_index.values():
                base_rows.extend(rows[:600])
        else:
            return []

        if not query_text:
            return [dict(row) for row in base_rows[:cap]]

        starts_with = []
        contains = []
        for row in base_rows:
            city = str(row.get("city") or "").lower()
            label = str(row.get("label") or "").lower()
            if city.startswith(query_text):
                starts_with.append(row)
            elif query_text in city or query_text in label:
                contains.append(row)

        ranked = starts_with + contains
        ranked.sort(key=lambda item: (-int(item.get("population") or 0), str(item.get("city") or "").lower()))
        return [dict(row) for row in ranked[:cap]]

    @classmethod
    def list_timezones(
        cls,
        *,
        country_code: str | None = None,
        query: str = "",
        limit: int = 500,
    ) -> list[str]:
        cap = max(1, min(int(limit or 500), 2000))
        query_text = (query or "").strip().lower()
        country = cls.normalize_country_code(country_code)
        country_index, _, _ = cls._build_city_indexes()

        if country and country in country_index:
            values = sorted({str(row.get("timezone") or "UTC") for row in country_index[country]})
        else:
            values = sorted(set(pytz.all_timezones))

        if query_text:
            values = [tz for tz in values if query_text in tz.lower()]
        return values[:cap]
