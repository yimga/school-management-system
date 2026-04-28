"""
Load the static platform pack catalog (workflow + dashboard pack manifests).

Install/apply remains governed elsewhere; this module is discovery-only.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from apps.siteconfig.commercial_tiers import (
    commercial_tier_for_school,
    normalize_commercial_tier_slug,
    tier_meets_minimum,
)

_ROOT = Path(__file__).resolve().parent / "data"
_CATALOG_PATH = _ROOT / "platform_pack_catalog.json"

_REQUIRED_PACK_KEYS = frozenset(
    {
        "pack_key",
        "school_type",
        "modules",
        "workflows",
        "dashboards",
        "policies",
        "theme",
        "required_apps",
        "version",
    }
)


def _normalize_pack_row(row: dict) -> dict:
    """Attach display defaults (optional monetization / gating metadata)."""
    r = dict(row)
    r.setdefault("pricing_type", "included_in_plan")
    r.setdefault("price_display", "")
    r.setdefault("required_commercial_tier", "")
    return r


def pack_row_entitled(school, row: dict | None) -> bool:
    """True when school's commercial tier meets pack ``required_commercial_tier`` (if any)."""
    if school is None or not isinstance(row, dict):
        return True
    req = normalize_commercial_tier_slug(row.get("required_commercial_tier"))
    if not req:
        return True
    return tier_meets_minimum(commercial_tier_for_school(school), req)


@lru_cache(maxsize=1)
def load_platform_pack_catalog() -> dict:
    raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    if int(raw.get("schema_version") or 0) < 1:
        raise ValueError("platform_pack_catalog: schema_version >= 1 required")
    for key in ("workflow_packs", "dashboard_packs", "theme_packs"):
        rows = raw.get(key)
        if isinstance(rows, list):
            raw[key] = [
                _normalize_pack_row(r) if isinstance(r, dict) else r for r in rows
            ]
    return raw


def validate_pack_entries(entries: list, *, kind: str) -> list[str]:
    warnings: list[str] = []
    for i, row in enumerate(entries):
        if not isinstance(row, dict):
            warnings.append(f"{kind}[{i}] is not an object")
            continue
        missing = sorted(_REQUIRED_PACK_KEYS - set(row.keys()))
        if missing:
            warnings.append(f"{kind}[{i}] missing keys: {', '.join(missing)}")
    return warnings


def validate_platform_pack_catalog(data: dict | None) -> list[str]:
    if not isinstance(data, dict):
        return ["catalog root must be an object"]
    w = []
    wf = data.get("workflow_packs") or []
    db = data.get("dashboard_packs") or []
    if not isinstance(wf, list):
        w.append("workflow_packs must be a list")
    else:
        w.extend(validate_pack_entries(wf, kind="workflow_packs"))
    if not isinstance(db, list):
        w.append("dashboard_packs must be a list")
    else:
        w.extend(validate_pack_entries(db, kind="dashboard_packs"))
    tp = data.get("theme_packs") or []
    if not isinstance(tp, list):
        w.append("theme_packs must be a list")
    else:
        w.extend(validate_pack_entries(tp, kind="theme_packs"))
    return w
