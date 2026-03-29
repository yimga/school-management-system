"""
Phase B Batches 4-13: physical per-domain snapshots for tenant site-settings ownership slices.

Each domain maps to one row in ``PlatformPhaseBDomainSnapshot`` (see
``PHASE_B_SNAPSHOT_DOMAINS``). ``brand_experience`` is excluded here — authority
for theme/media/report FKs stays in ``PlatformGlobalBranding`` (Batch 1).

In ``get_effective_site_settings``, snapshots merge **before**
``RuntimeDefaults.payload`` so the runtime payload wins on overlapping keys
(stale snapshot after direct RT updates).
"""

from __future__ import annotations

import hashlib
import json
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

# Do not duplicate provider secrets into snapshot rows (the slim tenant settings row remains write path;
# RuntimeDefaults typed secret columns are first-class, not in JSON payload).
_MARKETPLACE_SECRET_KEYS: Final[frozenset[str]] = frozenset(
    {
        "sms_api_key",
        "ai_provider_api_key",
        "whatsapp_api_token",
        "marksheet_ocr_api_key",
        "smtp_password",
        "webhook_signing_secret",
        "marketplace_partner_client_secret",
    }
)


def phase_b_top_level_key_fingerprints(payload: Any) -> dict[str, str]:
    """
    Per-key value fingerprints (top-level keys only).

    Enables operator diff without materializing one DB row per key; first-class tables per
    field remain a separate §11.4 sequencing track in SITECONFIG_OWNERSHIP_MIGRATION.md.
    """
    if not isinstance(payload, dict):
        return {}
    out: dict[str, str] = {}
    for key in sorted(payload.keys()):
        canonical = json.dumps(
            payload[key], sort_keys=True, separators=(",", ":"), default=str
        )
        out[key] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return out


def diff_top_level_payload_keys(
    live: dict[str, Any], stored: dict[str, Any]
) -> dict[str, Any]:
    """Summarize drift: keys only on one side, or same key with different canonical value."""
    lf = phase_b_top_level_key_fingerprints(live)
    sf = phase_b_top_level_key_fingerprints(stored)
    only_live = sorted(k for k in lf if k not in sf)
    only_stored = sorted(k for k in sf if k not in lf)
    value_mismatch = sorted(k for k in lf if k in sf and lf[k] != sf[k])
    return {
        "only_live": only_live,
        "only_stored": only_stored,
        "value_mismatch": value_mismatch,
        "changed_key_count": len(only_live) + len(only_stored) + len(value_mismatch),
    }


def phase_b_payload_metadata(payload: Any) -> tuple[int, str]:
    """
    Typed index for snapshot rows: top-level key count + sha256 of canonical JSON.

    Uses the same canonicalization as sync (sorted keys, compact separators) so
    control-plane diff can compare live ``owned_payload`` fingerprints to materialized rows.
    """
    if not isinstance(payload, dict):
        payload = {}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return len(payload), digest


def snapshot_payload_for_domain(site: Any, domain: str) -> dict[str, Any]:
    """Live slice for a Phase B domain (secrets stripped for marketplace_integrations)."""
    try:
        payload = dict(site.owned_payload(owner=domain))
    except Exception:
        payload = {}
    if domain == "marketplace_integrations":
        for k in _MARKETPLACE_SECRET_KEYS:
            payload.pop(k, None)
    return payload


def sync_phase_b_domain_snapshots_from_site(site: Any) -> None:
    """Persist per-domain payloads from the live slim tenant settings row (after save)."""
    if site is None or not getattr(site, "pk", None):
        return
    try:
        site.refresh_from_db()
    except Exception:
        pass

    from apps.platform_runtime.helpers import invalidate_effective_site_settings_cache
    from apps.platform_runtime.models import PlatformPhaseBDomainSnapshot

    for domain in PHASE_B_SNAPSHOT_DOMAINS:
        payload = snapshot_payload_for_domain(site, domain)
        key_count, checksum = phase_b_payload_metadata(payload)
        key_checksums = phase_b_top_level_key_fingerprints(payload)
        PlatformPhaseBDomainSnapshot.objects.update_or_create(
            domain=domain,
            defaults={
                "payload": payload,
                "payload_key_count": key_count,
                "payload_checksum": checksum,
                "payload_key_checksums": key_checksums,
            },
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
    """Overlay snapshot payloads onto the shallow tenant settings copy (before PGB merge)."""
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
