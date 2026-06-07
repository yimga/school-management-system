"""
Wave 2/3 — Apply marketplace capability bindings when sandbox → active (and revert on uninstall).
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from apps.marketplace.capability_contract import extract_capability_bindings

logger = logging.getLogger(__name__)

_CONFIG_FEATURES_KEY = "capability_features_enabled"
_CONFIG_ADAPTERS_KEY = "capability_integration_adapters"
_CONFIG_PACKAGES_KEY = "capability_packages_applied"


def _school_features_dict(school) -> dict[str, bool]:
    raw = getattr(school, "features", None) or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): bool(v) for k, v in raw.items()}


def _school_settings_dict(school) -> dict[str, Any]:
    raw = getattr(school, "settings", None) or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _enable_features(school, feature_codes: list[str]) -> list[str]:
    if not feature_codes:
        return []
    features = _school_features_dict(school)
    enabled: list[str] = []
    for code in feature_codes:
        c = str(code).strip().lower()
        if not c:
            continue
        if not features.get(c):
            features[c] = True
            enabled.append(c)
    if enabled:
        school.features = features
        school.save(update_fields=["features", "updated_at"])
        try:
            from apps.policies.resolver import invalidate_policy_cache

            invalidate_policy_cache(school)
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
    return enabled


def _disable_features_if_unused(school, feature_codes: list[str], *, exclude_app_slug: str) -> list[str]:
    """Turn off features enabled by this app if no other ACTIVE install still binds them."""
    from apps.marketplace.models import AppInstallation

    if not feature_codes:
        return []
    still_needed: set[str] = set()
    for inst in AppInstallation.objects.filter(
        school=school,
        status=AppInstallation.Status.ACTIVE,
        install_phase=AppInstallation.InstallPhase.ACTIVE,
        uninstalled_at__isnull=True,
    ).select_related("app"):
        if inst.app.slug == exclude_app_slug:
            continue
        manifest = inst.app.manifest if isinstance(inst.app.manifest, dict) else {}
        for b in extract_capability_bindings(manifest):
            if b.get("kind") == "feature" and b.get("target"):
                still_needed.add(str(b["target"]).strip().lower())
    features = _school_features_dict(school)
    cleared: list[str] = []
    for code in feature_codes:
        c = str(code).strip().lower()
        if c and c not in still_needed and features.get(c):
            features[c] = False
            cleared.append(c)
    if cleared:
        school.features = features
        school.save(update_fields=["features", "updated_at"])
        try:
            from apps.policies.resolver import invalidate_policy_cache

            invalidate_policy_cache(school)
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
    return cleared


def _record_integration_adapters(school, app_slug: str, adapters: list[str]) -> list[str]:
    if not adapters:
        return []
    from apps.marketplace.integration_adapter_credentials import (
        merge_credential_placeholders,
    )

    settings = _school_settings_dict(school)
    bucket = settings.get("marketplace_integration_adapters")
    if not isinstance(bucket, dict):
        bucket = {}
    recorded: list[str] = []
    for adapter in adapters:
        key = str(adapter).strip()
        if not key:
            continue
        bucket[key] = {"app_slug": app_slug, "status": "active"}
        recorded.append(key)
    if recorded:
        settings["marketplace_integration_adapters"] = bucket
        settings, _seeded = merge_credential_placeholders(
            settings,
            app_slug=app_slug,
            adapter_keys=recorded,
        )
        school.settings = settings
        school.save(update_fields=["settings", "updated_at"])
    return recorded


def _clear_integration_adapters(school, app_slug: str, adapters: list[str]) -> None:
    from apps.marketplace.integration_adapter_credentials import (
        clear_credential_placeholders,
    )

    settings = _school_settings_dict(school)
    bucket = settings.get("marketplace_integration_adapters")
    if not isinstance(bucket, dict):
        return
    for adapter in adapters:
        key = str(adapter).strip()
        entry = bucket.get(key)
        if isinstance(entry, dict) and entry.get("app_slug") == app_slug:
            bucket.pop(key, None)
    settings["marketplace_integration_adapters"] = bucket
    settings = clear_credential_placeholders(
        settings,
        app_slug=app_slug,
        adapter_keys=list(adapters),
    )
    school.settings = settings
    school.save(update_fields=["settings", "updated_at"])


def _try_apply_package(school, package_id: str, *, actor=None) -> bool:
    package_id = str(package_id or "").strip()
    if not package_id:
        return False
    try:
        from apps.packages.models import PackageVersion
        from apps.packages.engine import apply_package

        pv = (
            PackageVersion.objects.filter(package_id=package_id)
            .order_by("-created_at")
            .first()
        )
        if not pv or not (pv.payload_sections or {}):
            return False
        apply_package(
            school.pk,
            package_id,
            pv.version,
            dict(pv.payload_sections or {}),
            actor_id=getattr(actor, "pk", None) if actor else None,
        )
        return True
    except (ImportError, AttributeError, TypeError, ValueError, OSError) as exc:
        logger.debug("package apply skipped package_id=%s: %s", package_id, exc)
        return False


def _sync_widget_config(installation, manifest: dict[str, Any]) -> None:
    widgets = manifest.get("widgets")
    if isinstance(widgets, dict) and widgets:
        installation.widget_config = widgets
        installation.save(update_fields=["widget_config"])


@transaction.atomic
def apply_capability_bindings_on_activate(
    installation,
    *,
    manifest: dict[str, Any] | None = None,
    actor=None,
) -> dict[str, Any]:
    """Run after sandbox → active; persists audit payload on installation.config."""
    school = installation.school
    app = installation.app
    manifest = manifest if isinstance(manifest, dict) else (app.manifest or {})
    bindings = extract_capability_bindings(manifest)

    feature_codes = [
        b["target"] for b in bindings if b.get("kind") == "feature" and b.get("target")
    ]
    adapters = [
        b["target"]
        for b in bindings
        if b.get("kind") == "integration_adapter" and b.get("target")
    ]
    packages = [
        b["target"]
        for b in bindings
        if b.get("kind") == "package_id" and b.get("target")
    ]

    enabled = _enable_features(school, feature_codes)
    recorded_adapters = _record_integration_adapters(school, app.slug, adapters)
    applied_packages: list[str] = []
    for pid in packages:
        if _try_apply_package(school, pid, actor=actor):
            applied_packages.append(pid)

    _sync_widget_config(installation, manifest)

    cfg = dict(installation.config or {})
    cfg[_CONFIG_FEATURES_KEY] = enabled
    cfg[_CONFIG_ADAPTERS_KEY] = recorded_adapters
    cfg[_CONFIG_PACKAGES_KEY] = applied_packages
    installation.config = cfg
    installation.save(update_fields=["config"])

    return {
        "features_enabled": enabled,
        "integration_adapters": recorded_adapters,
        "packages_applied": applied_packages,
        "binding_count": len(bindings),
    }


@transaction.atomic
def revert_capability_bindings_on_uninstall(
    installation,
    *,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    school = installation.school
    app = installation.app
    manifest = manifest if isinstance(manifest, dict) else (app.manifest or {})
    cfg = dict(installation.config or {})

    feature_codes = cfg.get(_CONFIG_FEATURES_KEY) or [
        b["target"]
        for b in extract_capability_bindings(manifest)
        if b.get("kind") == "feature"
    ]
    adapters = cfg.get(_CONFIG_ADAPTERS_KEY) or [
        b["target"]
        for b in extract_capability_bindings(manifest)
        if b.get("kind") == "integration_adapter"
    ]

    cleared = _disable_features_if_unused(
        school, list(feature_codes), exclude_app_slug=app.slug
    )
    _clear_integration_adapters(school, app.slug, list(adapters))
    return {"features_cleared": cleared, "adapters_cleared": adapters}
