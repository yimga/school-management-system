"""Bridge payment baselines + deep LocalExperienceProfile for tenant command surfaces."""

from __future__ import annotations

from typing import Any

from apps.siteconfig.country_experience_baselines import baseline_index
from apps.siteconfig.country_localization_service import resolve_country_pack
from apps.siteconfig.local_experience_profiles import list_profiles


def _derive_education_from_localization(country_code: str) -> dict[str, Any]:
    """Synthesize academic metadata from localization seed when no deep profile exists."""
    pack = resolve_country_pack(country_code)
    calendar = pack.get("calendar_system") if isinstance(pack.get("calendar_system"), dict) else {}
    system_name = str(pack.get("system_name") or pack.get("label") or "").strip()
    calendar_code = str(calendar.get("code") or calendar.get("name") or "gregorian-3-term").strip()
    grading = str(pack.get("grading_default") or "percentage").strip()
    low_connectivity = bool(pack.get("low_connectivity_default", False))
    parent_engagement = str(pack.get("parent_engagement_default") or "weekly-summary").strip()
    return {
        "profile_key": f"{country_code.lower()}-derived",
        "academic_system": system_name or "international",
        "grading_system": grading,
        "calendar_system": calendar_code,
        "parent_engagement_default": parent_engagement,
        "low_connectivity_default": low_connectivity,
        "derived_from": "country_localization_pack",
    }


def resolve_local_experience_for_country(country_code: str) -> dict[str, Any]:
    """Return merged baseline + deep or derived profile metadata for ISO2."""
    code = str(country_code or "").strip().upper()[:2]
    if not code:
        return {"configured": False, "depth": "none"}
    baseline = baseline_index().get(code)
    profiles = list_profiles(country=code)
    deep = profiles[0] if profiles else None
    derived = None if deep else _derive_education_from_localization(code)
    has_derived = bool(derived and derived.get("academic_system"))
    if baseline is None and not deep and not has_derived:
        return {"configured": False, "depth": "none", "country_code": code}
    if deep:
        depth = "deep"
    elif has_derived:
        depth = "derived"
    else:
        depth = "baseline"
    out: dict[str, Any] = {
        "configured": True,
        "country_code": code,
        "depth": depth,
        "profile_count": len(profiles),
    }
    if baseline is not None:
        out.update(
            {
                "label": baseline.label,
                "currency": baseline.currency,
                "primary_rail": baseline.primary_rail,
                "template_depth": baseline.template_depth,
            }
        )
    if deep:
        out.update(
            {
                "profile_key": deep.get("key"),
                "academic_system": deep.get("academic_system"),
                "grading_system": deep.get("grading_system"),
                "parent_engagement_default": deep.get("parent_engagement_default"),
                "low_connectivity_default": deep.get("low_connectivity_default"),
            }
        )
    elif has_derived:
        out.update(derived)
    return out


def count_configured_countries() -> dict[str, int]:
    """Coverage stats for verifiers — deep, derived, baseline-only."""
    index = baseline_index()
    deep = derived = baseline_only = 0
    for code in index:
        row = resolve_local_experience_for_country(code)
        if not row.get("configured"):
            continue
        depth = row.get("depth")
        if depth == "deep":
            deep += 1
        elif depth == "derived":
            derived += 1
        else:
            baseline_only += 1
    return {
        "total_baselines": len(index),
        "deep": deep,
        "derived": derived,
        "baseline_only": baseline_only,
        "configured": deep + derived + baseline_only,
    }


__all__ = ["resolve_local_experience_for_country", "count_configured_countries"]
