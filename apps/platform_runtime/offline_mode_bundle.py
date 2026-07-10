"""
Canonical offline-mode feature bundle for online (Render) and edge (LAN hub) schools.

School operations offline (queue + sync) is separate from live AI; see
docs/LOCAL_HUB_MODE.md and docs/RESILIENT_EDGE_IMPLEMENTATION_STATUS.md.
"""

from __future__ import annotations

from typing import Any

# Policy-owned master switch (RuntimeDefaults / feature control).
OFFLINE_MODE_FIELD_UPDATES: dict[str, object] = {
    "enable_offline_mode": True,
}

# Backend feature flags merged into existing tenant flags (preserves other keys).
OFFLINE_MODE_BACKEND_FLAG_UPDATES: dict[str, object] = {
    "enable_offline_form_queue": True,
    "enable_offline_intake_wizard": True,
    "enable_offline_attendance_sync": True,
    "enable_offline_proximity_attendance_sync": True,
    "enable_offline_grade_sync": True,
    "enable_offline_homework_sync": True,
    "enable_offline_payment_sync": True,
    "enable_offline_background_sync": True,
    "enable_offline_queue_encryption": True,
    "show_offline_status_bar": True,
    "offline_entity_sync": True,
    "offline_requests_sync": True,
    "request_persistent_browser_storage": True,
    "reachability_url": "/health/",
}


def merged_backend_flags_for_offline_bundle(
    existing: dict[str, object] | None,
) -> dict[str, object]:
    base = dict(existing or {})
    base.update(OFFLINE_MODE_BACKEND_FLAG_UPDATES)
    return base


def apply_offline_mode_bundle_for_tenant(
    *,
    hub_base_url: str = "",
    dry_run: bool = False,
    tenant_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Apply the offline bundle to the current schema's SiteSettings (tenant context).

    Call inside ``tenant_context`` for multi-tenant schools. When ``tenant_manifest``
    is supplied (country-enriched offline manifest from
    ``apps.sync_engine.tenant_manifest_resolver``) it is persisted under the
    ``offline_tenant_manifest`` backend flag so the edge/PWA layer can read the
    tenant's locale, country pack summary, and HONEST payment posture offline.
    """
    from apps.platform_runtime.helpers import get_platform_site_settings_record

    # config-resolver-allow: write-path singleton (create=True; row mutated via apply_feature_control_state)
    site = get_platform_site_settings_record(create=True)
    bff = merged_backend_flags_for_offline_bundle(site.get_backend_feature_flags())
    hub = (hub_base_url or "").strip()
    if hub:
        bff["hub_base_url"] = hub.rstrip("/")
    if tenant_manifest:
        bff["offline_tenant_manifest"] = tenant_manifest
    if dry_run:
        return {
            "dry_run": True,
            "enable_offline_mode": True,
            "backend_flags": bff,
            "offline_tenant_manifest": tenant_manifest,
        }
    site.apply_feature_control_state(
        backend_feature_flags=bff,
        field_updates=dict(OFFLINE_MODE_FIELD_UPDATES),
    )
    return {
        "dry_run": False,
        "enable_offline_mode": True,
        "hub_base_url": bff.get("hub_base_url", ""),
    }


def _enable_offline_mode_policy_module(school, *, dry_run: bool = False) -> bool:
    """
    Policy Registry gate: ``OFFLINE_ENABLED_FOR_CURRENT_SCHOOL`` requires
    ``get_effective_policy(..., capability="offline_mode").enabled`` in addition
    to ``enable_offline_mode`` in Feature Control.
    """
    feats = dict(getattr(school, "features", None) or {})
    if feats.get("offline_mode"):
        # Already enabled — the module IS on. The caller stores this return as the
        # `offline_mode_module_enabled` STATE field, so an idempotent re-apply must
        # report True (enabled), not False (which read as "not enabled").
        return True
    if dry_run:
        return True
    feats["offline_mode"] = True
    school.features = feats
    school.save(update_fields=["features", "updated_at"])
    try:
        from apps.policies.policy_registry import invalidate_policy_cache

        invalidate_policy_cache(school)
    except Exception:
        import logging

        logging.getLogger(__name__).debug(
            "invalidate_policy_cache after offline_mode module enable failed",
            exc_info=True,
        )
    return True


def apply_offline_mode_bundle_for_school(
    school,
    *,
    hub_base_url: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply bundle inside the school's tenant schema when django-tenants is enabled."""
    from apps.schools.tasks import _ensure_tenant_client, _optional_tenant_context

    # Country-enriched offline manifest (the country-profile -> manifest -> offline
    # chain link). Resolved from the school BEFORE entering tenant context; a
    # resolution failure must never break provisioning, so it is best-effort.
    tenant_manifest: dict[str, Any] | None = None
    try:
        from apps.sync_engine.tenant_manifest_resolver import school_offline_manifest_dict

        tenant_manifest = school_offline_manifest_dict(school)
    except Exception:
        import logging

        logging.getLogger(__name__).debug(
            "offline tenant manifest resolve failed for school %s",
            getattr(school, "id", school),
            exc_info=True,
        )

    client = _ensure_tenant_client(school)
    with _optional_tenant_context(client):
        result = apply_offline_mode_bundle_for_tenant(
            hub_base_url=hub_base_url,
            dry_run=dry_run,
            tenant_manifest=tenant_manifest,
        )
    result["offline_mode_module_enabled"] = _enable_offline_mode_policy_module(
        school, dry_run=dry_run
    )
    return result


def maybe_apply_offline_bundle_on_provision(school) -> None:
    """
    Called at end of school provisioning when RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION is on.
    """
    import os

    from django.conf import settings

    raw = (
        getattr(settings, "RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION", None)
        or os.environ.get("RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION", "1")
    )
    if str(raw).strip().lower() not in ("1", "true", "yes", "on"):
        return
    hub = ""
    profile = (
        getattr(settings, "RMC_DEPLOYMENT_PROFILE", None)
        or os.environ.get("RMC_DEPLOYMENT_PROFILE", "online")
        or "online"
    ).strip().lower()
    if profile in ("hybrid", "edge"):
        hub = (
            getattr(settings, "RMC_HUB_BASE_URL", None)
            or os.environ.get("RMC_HUB_BASE_URL", "")
            or ""
        ).strip()
    try:
        apply_offline_mode_bundle_for_school(school, hub_base_url=hub)
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "offline_mode_bundle apply failed for school %s",
            getattr(school, "id", school),
            exc_info=True,
        )
