"""School.settings[\"data_residency\"] JSON bridge (GEOS-99 batch 1388).

Regulatory residency is stored in ``School.data_region``; this module mirrors
and validates an optional ``settings[\"data_residency\"]`` object for operator
APIs and middleware guards.
"""

from __future__ import annotations

from typing import Any

from apps.schools.data_residency import CANONICAL_REGIONS, derive_default_region


def get_data_residency_payload(school) -> dict[str, Any]:
    """Return normalized residency dict from settings JSON + data_region field."""
    raw = {}
    if school is not None:
        settings_json = getattr(school, "settings", None) or {}
        if isinstance(settings_json, dict):
            raw = settings_json.get("data_residency") or {}
        region = getattr(school, "data_region", None) or derive_default_region(
            getattr(school, "country_code", "") or ""
        )
    else:
        region = "global"
    code = (raw.get("region_code") or region or "global").strip().lower()
    return {
        "region_code": code,
        "enforcement": raw.get("enforcement") or "audit",
        "corridor_id": raw.get("corridor_id") or "",
        "canonical": code in CANONICAL_REGIONS or code == "global",
    }


def set_data_residency_payload(school, payload: dict[str, Any]) -> None:
    """Persist residency object into School.settings (does not save)."""
    if not isinstance(school.settings, dict):
        school.settings = {}
    school.settings["data_residency"] = {
        "region_code": (payload.get("region_code") or school.data_region or "global").strip().lower(),
        "enforcement": payload.get("enforcement") or "audit",
        "corridor_id": (payload.get("corridor_id") or "").strip(),
    }
    if payload.get("region_code"):
        school.data_region = school.settings["data_residency"]["region_code"]


def residency_middleware_guard(school, request_region: str | None) -> bool:
    """Return True when request region aligns with tenant residency (soft guard)."""
    payload = get_data_residency_payload(school)
    if payload.get("enforcement") != "strict":
        return True
    expected = payload.get("region_code") or "global"
    if not request_region or expected == "global":
        return True
    return request_region.strip().lower() == expected


__all__ = [
    "get_data_residency_payload",
    "residency_middleware_guard",
    "set_data_residency_payload",
]
