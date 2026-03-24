"""
Phase 9 — cross-surface links for marketplace ↔ migration ↔ packs ↔ interop (tenant URLconf).

Safe reverses only; empty string when a name is not mounted on the active urlconf.
"""

from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse


def safe_reverse(viewname: str, *, kwargs: dict[str, Any] | None = None) -> str:
    try:
        if kwargs:
            return reverse(viewname, kwargs=kwargs)
        return reverse(viewname)
    except NoReverseMatch:
        return ""


def build_phase9_ecosystem_links() -> dict[str, str]:
    """
    URLs commonly needed to stitch ecosystem workflows together on a tenant host.
    """
    return {
        "tenant_app_catalog": safe_reverse("tenant_app_catalog"),
        "tenant_installed_apps": safe_reverse("tenant_installed_apps"),
        "migration_wizard": safe_reverse("accounts:migration_wizard"),
        "migration_run_list": safe_reverse("accounts:migration_run_list"),
        "district_interop": safe_reverse("accounts:district_lms_interop"),
        "apicenter": safe_reverse("apicenter:dashboard"),
        "import_hub": safe_reverse("studio_os:import_hub"),
        "workflow_center": safe_reverse("studio_os:workflow_center"),
        "pack_rollback": safe_reverse("siteconfig:installed_packages_rollback"),
        "ai_migration_suggest": safe_reverse("api:ai-migration-suggest"),
    }
