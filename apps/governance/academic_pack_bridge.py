"""Bridge country governance matrix rows to localization packs and grading presets."""

from __future__ import annotations

from typing import Any

from apps.governance.country_matrix_service import get_matrix_row
from apps.siteconfig.country_localization_service import resolve_country_pack

# Maps localization pack regional keys + region buckets to Education DNA preset keys.
_GRADING_PRESET_BY_REGIONAL: dict[str, str] = {
    "africa-francophone": "francophone_bac",
    "africa-anglophone": "west_african_waec",
    "africa-arabic": "american",
    "caribbean": "british_igcse",
    "east-asia": "east_asia_competitive",
    "europe-continental": "american",
    "europe-eastern": "east_asia_competitive",
    "europe-nordic": "american",
    "europe-romance": "francophone_bac",
    "latam-portuguese": "american",
    "latam-spanish": "american",
    "middle-east": "british_igcse",
    "oceania": "british_igcse",
    "south-asia": "british_igcse",
    "southeast-asia": "east_asia_competitive",
    "generic": "american",
}

_GRADING_PRESET_BY_BUCKET: dict[str, str] = {
    "africa": "west_african_waec",
    "europe": "british_igcse",
    "americas": "american",
    "asia": "east_asia_competitive",
    "oceania": "british_igcse",
}


def _normalize_iso(country_code: str | None) -> str:
    cc = (country_code or "").strip().upper()
    if len(cc) == 2 and cc.isalpha():
        return cc
    return ""


def pack_source_tier(source: str) -> str:
    src = str(source or "")
    if src.startswith("country:"):
        return "tier1_native"
    if src.startswith("regional:") and src not in ("regional:generic", ""):
        return "tier1_regional_clone"
    return "generic_fallback"


def resolve_grading_preset_key(country_code: str | None) -> str:
    """Return Education DNA / profile grading preset key for any ISO alpha-2."""
    iso = _normalize_iso(country_code)
    pack = resolve_country_pack(iso) if iso else {}
    source = str(pack.get("_source") or "")
    if source.startswith("regional:"):
        region_key = source.split(":", 1)[-1]
        preset = _GRADING_PRESET_BY_REGIONAL.get(region_key)
        if preset:
            return preset
    row = get_matrix_row(iso) if iso else None
    if row:
        bucket = str(row.get("region_bucket") or "")
        return _GRADING_PRESET_BY_BUCKET.get(bucket, "american")
    return "american"


def resolve_academic_pack_context(country_code: str | None) -> dict[str, Any]:
    """
    Unified payload for signup, runtime structural-options, and policy merge.
    """
    iso = _normalize_iso(country_code)
    pack = resolve_country_pack(iso) if iso else {}
    row = get_matrix_row(iso) if iso else None
    source = str(pack.get("_source") or "")
    matrix_tier = str((row or {}).get("education_pack_tier") or "")
    live_tier = pack_source_tier(source)
    exam_boards = []
    if row and isinstance(row.get("exam_boards"), list):
        exam_boards = list(row.get("exam_boards") or [])
    supports_multi_shift = False
    if source.startswith("regional:latam"):
        supports_multi_shift = True
    if row and str(row.get("region_bucket") or "") == "americas":
        latam_codes = {"AR", "BO", "BR", "CL", "CO", "CR", "CU", "DO", "EC", "GT", "HN", "MX", "NI", "PA", "PE", "PY", "SV", "UY", "VE"}
        if iso in latam_codes:
            supports_multi_shift = True

    return {
        "iso_alpha2": iso,
        "country_pack": pack,
        "matrix_row": row or {},
        "pack_source": source,
        "education_pack_tier_live": live_tier,
        "education_pack_tier_matrix": matrix_tier,
        "pack_tier_aligned": (not matrix_tier) or (matrix_tier == live_tier),
        "governance_archetype": str((row or {}).get("governance_archetype") or ""),
        "grading_preset_key": resolve_grading_preset_key(iso),
        "exam_boards": exam_boards,
        "supports_multi_shift": supports_multi_shift,
        "school_types": pack.get("school_types") or [],
        "education_levels": pack.get("education_levels") or [],
        "terminology": pack.get("terminology") or {},
    }


def audit_pack_matrix_alignment(rows: list[dict[str, Any]]) -> list[str]:
    """Return mismatch lines between matrix education_pack_tier and live pack source."""
    failures: list[str] = []
    for row in rows:
        iso = str(row.get("iso_alpha2") or "")
        if not iso:
            continue
        pack = resolve_country_pack(iso)
        source = str(pack.get("_source") or "")
        live = pack_source_tier(source)
        matrix_tier = str(row.get("education_pack_tier") or "")
        if matrix_tier and matrix_tier != live:
            failures.append(f"{iso}: matrix {matrix_tier} != live {live} ({source})")
    return failures
