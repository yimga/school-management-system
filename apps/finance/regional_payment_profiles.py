"""
Regional payment corridor metadata (primary/backup rails, offline receipt policy).

Used by invoice UI and payment fallback selection — does not replace billing enforcement.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_FILE = Path(__file__).resolve().parent / "data" / "regional_payment_profiles.json"


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    if not _DATA_FILE.is_file():
        return {}
    return json.loads(_DATA_FILE.read_text(encoding="utf-8"))


def get_regional_profile(country_code: str | None) -> dict[str, Any] | None:
    """Return profile dict for ISO country code, or None."""
    if not country_code:
        return None
    key = str(country_code).strip().upper()[:8]
    data = _load_raw()
    row = data.get(key)
    if isinstance(row, dict):
        return dict(row)
    return None


def list_supported_country_codes() -> list[str]:
    return sorted(_load_raw().keys())


def clear_profile_cache() -> None:
    _load_raw.cache_clear()
