"""
Phase 9 — normalize marketplace listing fields for tenant/control-plane catalog UIs.
"""

from __future__ import annotations

from typing import Any

from apps.marketplace.models import MarketplaceListing


def catalog_listing_display(listing: MarketplaceListing) -> dict[str, Any]:
    """
    Merge JSON compatibility + AppVersionCompat rows into template-friendly dicts.
    """
    raw = listing.compatibility if isinstance(listing.compatibility, dict) else {}
    vcs = list(listing.app.version_compat.all()[:3])
    primary = vcs[0] if vcs else None
    return {
        "countries": raw.get("countries") or [],
        "plan_tiers": raw.get("plan_tiers") or [],
        "blueprint_families": raw.get("blueprint_families") or [],
        "workflow_families": raw.get("workflow_families") or [],
        "recommended_sectors": raw.get("recommended_sectors") or [],
        "min_rmc_version": raw.get("min_rmc_version") or "",
        "platform_min_version": getattr(primary, "platform_min_version", "") or "",
        "app_version_range": _format_version_range(primary),
        "compat_notes": getattr(primary, "notes", "") if primary else "",
        "sandbox_recommended": bool(raw.get("sandbox_recommended", True)),
        "rollback_summary": raw.get(
            "rollback_summary",
            "Sandbox first; uninstall or deactivate from Installed apps; metadata packs use Pack rollback.",
        ),
    }


def _format_version_range(vc: Any) -> str:
    if not vc:
        return ""
    lo = (getattr(vc, "app_version_min", None) or "").strip()
    hi = (getattr(vc, "app_version_max", None) or "").strip()
    if lo and hi:
        return f"{lo} – {hi}"
    if lo:
        return f"≥ {lo}"
    if hi:
        return f"≤ {hi}"
    return ""
