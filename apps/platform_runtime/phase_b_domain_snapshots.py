"""
Phase B Batches 4-13: physical per-domain snapshots for SiteSettings ownership slices.

Each domain maps to one row in ``PlatformPhaseBDomainSnapshot`` (see
``PHASE_B_SNAPSHOT_DOMAINS``). ``brand_experience`` is excluded here — authority
for theme/media/report FKs stays in ``PlatformGlobalBranding`` (Batch 1).

In ``get_effective_site_settings``, snapshots merge **before**
``RuntimeDefaults.payload`` so the runtime payload wins on overlapping keys
(stale snapshot after direct RT updates).
"""

from __future__ import annotations

from typing import Any, Final

# Stable merge order: ``policies_rules`` last so portal/feature flags win on any overlap.
PHASE_B_SNAPSHOT_DOMAINS: Final[tuple[str, ...]] = (
    "design_studio",
    "documents",
    "global_registries",
    "marketplace_integrations",
    "metadata_governance",
    "plans_entitlements",
    "preview_platform",
    "reports",
    "runtime_blueprints",
    "policies_rules",
)

# Do not duplicate provider secrets into snapshot rows (SiteSettings remains write path).
_MARKETPLACE_SECRET_KEYS: Final[frozenset[str]] = frozenset({"sms_api_key"})


def sync_phase_b_domain_snapshots_from_site(site: Any) -> None:
    """Persist per-domain payloads from the live SiteSettings row (after save)."""
    if site is None or not getattr(site, "pk", None):
        return
    try:
        site.refresh_from_db()
    except Exception:
        pass

    from apps.platform_runtime.helpers import invalidate_effective_site_settings_cache
    from apps.platform_runtime.models import PlatformPhaseBDomainSnapshot

    for domain in PHASE_B_SNAPSHOT_DOMAINS:
        try:
            payload = dict(site.owned_payload(owner=domain))
        except Exception:
            payload = {}
        if domain == "marketplace_integrations":
            for k in _MARKETPLACE_SECRET_KEYS:
                payload.pop(k, None)
        PlatformPhaseBDomainSnapshot.objects.update_or_create(
            domain=domain, defaults={"payload": payload}
        )
    try:
        invalidate_effective_site_settings_cache()
    except Exception:
        pass
    try:
        from apps.policies.resolver import invalidate_all_tenant_policy_caches

        invalidate_all_tenant_policy_caches()
    except Exception:
        pass


def merge_phase_b_domain_snapshots_into_base(base: Any) -> None:
    """Overlay snapshot payloads onto the shallow SiteSettings copy (before PGB merge)."""
    from apps.platform_runtime.helpers import apply_payload_dict_to_site_settings_shallow_base
    from apps.platform_runtime.models import PlatformPhaseBDomainSnapshot

    combined: dict[str, Any] = {}
    try:
        for domain in PHASE_B_SNAPSHOT_DOMAINS:
            row = PlatformPhaseBDomainSnapshot.objects.filter(pk=domain).first()
            if row and isinstance(row.payload, dict) and row.payload:
                combined.update(row.payload)
    except Exception:
        return
    if combined:
        apply_payload_dict_to_site_settings_shallow_base(base, combined)
