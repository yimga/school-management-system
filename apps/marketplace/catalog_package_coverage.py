"""
Package binding coverage: every catalog slug uses legacy OR catalog-native PackageVersion.
"""

from __future__ import annotations

from apps.marketplace.legacy_package_bindings import (
    CATALOG_SLUG_TO_LEGACY_PACKAGE_ID,
    resolve_activate_package_id,
    resolve_legacy_package_id,
)
from apps.marketplace.management.commands.seed_marketplace_apps import FIRST_PARTY_APPS


def package_binding_mode(slug: str) -> str:
    return "legacy" if resolve_legacy_package_id(slug) else "catalog_native"


def catalog_native_slugs() -> list[str]:
    return [
        app["slug"]
        for app in FIRST_PARTY_APPS
        if app.get("slug") and not resolve_legacy_package_id(app["slug"])
    ]


def legacy_mapped_slugs() -> list[str]:
    return sorted(CATALOG_SLUG_TO_LEGACY_PACKAGE_ID.keys())


def catalog_package_coverage_errors() -> list[str]:
    """All 73 slugs resolve to a PackageVersion with non-empty payload_sections."""
    from apps.packages.models import PackageVersion

    errors: list[str] = []
    for app_def in FIRST_PARTY_APPS:
        slug = str(app_def.get("slug") or "").strip()
        if not slug:
            continue
        version = str(app_def.get("version") or "1.0").strip()
        package_id = resolve_activate_package_id(slug, app_def.get("manifest") or {})
        mode = package_binding_mode(slug)
        pv = (
            PackageVersion.objects.filter(package_id=package_id, version=version)
            .order_by("-created_at")
            .first()
        )
        if pv is None:
            pv = (
                PackageVersion.objects.filter(package_id=package_id)
                .order_by("-created_at")
                .first()
            )
        if pv is None:
            errors.append(f"{slug}: missing PackageVersion for {package_id} ({mode})")
            continue
        if not (pv.payload_sections or {}):
            errors.append(f"{slug}: empty payload on {package_id} ({mode})")
    return errors
