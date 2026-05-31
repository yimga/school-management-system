"""Read-only access to the country governance matrix shards (Phase 3A/3C)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings

_REPO_ROOT = Path(settings.BASE_DIR)
_MATRIX_PATH = _REPO_ROOT / "docs" / "generated" / "country_governance_matrix.json"
_SHARD_DIR = _REPO_ROOT / "docs" / "generated" / "country_governance_matrix"


def _normalize_country_code(country_code: str | None) -> str | None:
    if not country_code:
        return None
    iso = str(country_code).strip().upper()
    if len(iso) != 2 or not iso.isalpha():
        return None
    return iso


@lru_cache(maxsize=512)
def _load_shard(iso_alpha2: str) -> dict | None:
    shard_path = _SHARD_DIR / f"{iso_alpha2}.json"
    if shard_path.is_file():
        try:
            payload = json.loads(shard_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None
    return None


@lru_cache(maxsize=1)
def _load_matrix_rows_by_iso() -> dict[str, dict]:
    if not _MATRIX_PATH.is_file():
        return {}
    try:
        payload = json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        iso = _normalize_country_code(row.get("iso_alpha2"))
        if iso:
            out[iso] = row
    return out


def get_matrix_row(country_code: str | None) -> dict | None:
    """
    Return the governance matrix row for ``country_code`` (ISO 3166-1 alpha-2).

    Prefers per-country shard files under ``docs/generated/country_governance_matrix/``
    and falls back to the monolithic ``country_governance_matrix.json`` index.
    """
    iso = _normalize_country_code(country_code)
    if not iso:
        return None

    shard_row = _load_shard(iso)
    if shard_row is not None:
        return shard_row

    return _load_matrix_rows_by_iso().get(iso)


def _ministry_label_from_row(row: dict[str, Any]) -> str:
    local = row.get("local_terminology")
    if not isinstance(local, dict):
        return ""
    ministry = local.get("ministry_name")
    if not isinstance(ministry, dict):
        return ""
    label = ministry.get("en")
    if label:
        return str(label).strip()
    for value in ministry.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def statutory_framework_note_from_row(row: dict[str, Any]) -> str:
    """Build a statutory narrative from matrix fields (249-country fallback)."""
    ref = row.get("statutory_framework_ref")
    if ref:
        return str(ref).strip()

    parts: list[str] = []
    ministry = _ministry_label_from_row(row)
    if ministry:
        parts.append(f"{ministry} reporting alignment.")

    tier = str(row.get("education_pack_tier") or "generic_fallback")
    if tier == "tier1_native":
        parts.append("Native country education pack installed.")
    elif tier == "tier1_regional_clone":
        parts.append("Regional education pack clone — verify local statutory connectors.")
    else:
        parts.append(
            "Generic fallback pack — configure region and statutory connectors before filing."
        )

    archetype = str(row.get("governance_archetype") or "")
    if archetype == "state_emis_hub":
        parts.append("State EMIS hub archetype — aggregate reporting expected.")
    elif archetype == "district_trust_overlay":
        parts.append("District/trust overlay — LEA returns may apply.")

    return " ".join(parts)


def resolve_statutory_jurisdiction_hint(country_code: str | None) -> dict[str, str]:
    """
    Return ``{label, framework}`` for ministry/statutory shells.

    Curated catalog entries win; otherwise derive from the governance matrix
    so all 249 ISO codes resolve without hardcoded per-country branches.
    """
    iso = _normalize_country_code(country_code)
    if not iso:
        return {
            "label": "Unknown jurisdiction",
            "framework": "Configure region pack and statutory connectors.",
        }

    from apps.platform_runtime.learning_institution_catalog import (
        STATUTORY_JURISDICTION_HINTS,
    )

    curated = STATUTORY_JURISDICTION_HINTS.get(iso)
    if curated:
        return dict(curated)

    row = get_matrix_row(iso)
    if row:
        name = str(row.get("name_en") or iso)
        return {
            "label": name,
            "framework": statutory_framework_note_from_row(row),
        }

    return {
        "label": f"Jurisdiction ({iso})",
        "framework": "Configure region pack and statutory connectors.",
    }


def signup_governance_defaults(country_code: str | None) -> dict[str, Any]:
    """
    Matrix-driven signup payload for ``school.settings['governance']``.

    Standalone mode is always the default at public signup; country matrix only
    recommends archetype labels and admin-level vernacular — never forces a group.
    """
    iso = _normalize_country_code(country_code)
    row = get_matrix_row(iso) if iso else None
    if not row:
        return {
            "matrix_iso": iso or "",
            "operating_mode": "standalone",
            "governance_archetype": "single_org_multi_site",
            "admin_level_labels": [],
            "employer_model": "",
            "governance_inherit": {},
        }

    admin_levels = row.get("admin_levels")
    if not isinstance(admin_levels, list):
        admin_levels = []

    from apps.governance.academic_pack_bridge import resolve_academic_pack_context

    pack_ctx = resolve_academic_pack_context(iso)
    return {
        "matrix_iso": iso,
        "operating_mode": "standalone",
        "governance_archetype": str(row.get("governance_archetype") or "single_org_multi_site"),
        "admin_level_labels": admin_levels,
        "employer_model": str(row.get("employer_model") or ""),
        "education_pack_tier": str(row.get("education_pack_tier") or pack_ctx.get("education_pack_tier_live") or ""),
        "education_pack_tier_live": pack_ctx.get("education_pack_tier_live") or "",
        "pack_source": pack_ctx.get("pack_source") or "",
        "pack_tier_aligned": bool(pack_ctx.get("pack_tier_aligned")),
        "grading_preset_key": pack_ctx.get("grading_preset_key") or "",
        "supports_multi_shift": bool(pack_ctx.get("supports_multi_shift")),
        "exam_boards": pack_ctx.get("exam_boards") or [],
        "governance_inherit": {},
    }


def matrix_admin_labels(country_code: str | None) -> list[dict[str, Any]]:
    """Admin-level vernacular labels for Group Console / signup chrome."""
    row = get_matrix_row(country_code)
    if not row:
        return []
    levels = row.get("admin_levels")
    return list(levels) if isinstance(levels, list) else []
