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


def normalize_regional_profile_row(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Merge singular primary/backup rail fields with legacy list fields.
    Ensures primary_rail, backup_rail, manual_fallback, reconciliation_required, provider_notes.
    """
    if not raw or not isinstance(raw, dict):
        return None
    out = dict(raw)
    primaries = list(out.get("primary_rails") or [])
    backups = list(out.get("backup_rails") or [])
    out["primary_rail"] = str(out.get("primary_rail") or (primaries[0] if primaries else "") or "")
    out["backup_rail"] = str(out.get("backup_rail") or (backups[0] if backups else "") or "")
    if "manual_fallback" not in out:
        out["manual_fallback"] = bool(out.get("manual_receipt_allowed", True))
    if "reconciliation_required" not in out:
        out["reconciliation_required"] = bool(
            out.get("manual_receipt_allowed", True) or out.get("offline_receipt_allowed", False)
        )
    pn = out.get("provider_notes")
    out["provider_notes"] = str(pn if pn is not None else out.get("notes") or "")
    steps = out.get("operator_setup_steps")
    if not isinstance(steps, list):
        out["operator_setup_steps"] = []
    else:
        out["operator_setup_steps"] = [str(s) for s in steps if s is not None]
    tenant_steps = out.get("tenant_setup_steps")
    if not isinstance(tenant_steps, list):
        out["tenant_setup_steps"] = list(out["operator_setup_steps"])
    else:
        out["tenant_setup_steps"] = [str(s) for s in tenant_steps if s is not None]
    if not out["tenant_setup_steps"] and out["operator_setup_steps"]:
        out["tenant_setup_steps"] = list(out["operator_setup_steps"])
    pss = out.get("provider_setup_status")
    out["provider_setup_status"] = str(pss).strip() if pss else "external_required"
    orl = out.get("operator_ready_label")
    out["operator_ready_label"] = str(orl).strip() if orl else (
        "Corridor catalog loaded — complete tenant processor onboarding and rail linkage."
    )
    return out


def get_normalized_regional_profile(country_code: str | None) -> dict[str, Any] | None:
    """Profile with normalized singular rail fields and operator metadata."""
    base = get_regional_profile(country_code)
    return normalize_regional_profile_row(base)


def list_supported_country_codes() -> list[str]:
    return sorted(_load_raw().keys())


def clear_profile_cache() -> None:
    _load_raw.cache_clear()
