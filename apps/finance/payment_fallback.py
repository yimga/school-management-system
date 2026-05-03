"""
Payment fallback selection from regional corridor + invoice compliance profile.

Read-only advisory for UX and reconciliation hints — billing rules remain authoritative.
"""

from __future__ import annotations

from typing import Any

from apps.finance.regional_payment_profiles import (
    get_normalized_regional_profile,
    get_regional_profile,
)


def corridor_bundle_for_invoice(invoice: Any) -> dict[str, Any]:
    """
    Build a small dict for templates/API: primary rail, backups, flags.

    Expects ``invoice.profile.country_code`` / ``currency_code`` when present.
    """
    profile = getattr(invoice, "profile", None)
    cc = getattr(profile, "country_code", None) if profile else None
    currency = getattr(profile, "currency_code", None) if profile else None
    regional = get_regional_profile(cc) or {}
    normalized = get_normalized_regional_profile(cc) or {}
    primary = (regional.get("primary_rails") or ["BANK"])[:3]
    backup = (regional.get("backup_rails") or [])[:5]
    return {
        "country_code": cc,
        "currency_code": currency,
        "label": regional.get("label"),
        "primary_rails": primary,
        "backup_rails": backup,
        "primary_rail": normalized.get("primary_rail") or (primary[0] if primary else None),
        "backup_rail": normalized.get("backup_rail") or (backup[0] if backup else None),
        "manual_fallback": bool(normalized.get("manual_fallback", True)),
        "manual_receipt_allowed": bool(regional.get("manual_receipt_allowed", True)),
        "offline_receipt_allowed": bool(regional.get("offline_receipt_allowed", False)),
        "reconciliation_required": bool(normalized.get("reconciliation_required", False)),
        "reconciliation_hint": regional.get("reconciliation") or "",
        "notes": regional.get("notes") or "",
        "provider_notes": normalized.get("provider_notes") or "",
        "operator_setup_steps": normalized.get("operator_setup_steps") or [],
        "primary_method": primary[0] if primary else None,
        "backup_method": backup[0] if backup else None,
    }


def select_fallback_chain(country_code: str | None) -> list[str]:
    """Ordered rail preference: primary rails first, then backups (deduped)."""
    regional = get_regional_profile(country_code) or {}
    out: list[str] = []
    for bucket in (regional.get("primary_rails") or [], regional.get("backup_rails") or []):
        for r in bucket:
            if r and r not in out:
                out.append(str(r))
    return out
