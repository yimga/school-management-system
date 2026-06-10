"""
Tenant manifest resolver — the chain-reaction bridge.

`tenant_manifest_compiler.compile_manifest` is a deliberately narrow, deterministic
primitive: it takes whatever the caller hands it and produces a signed, scrubbed
offline-sync manifest. Until now nothing in the live product called it, so the
"country profile -> manifest -> offline" chain was unproven (see
docs/generated/local_first_chain_reaction_truth_audit_2026_06_10.md).

This module is the missing link. It reads a school's country and resolves, from the
existing read-only registries, exactly what the offline / PWA layer needs:

  * locale_default        <- country_localization_service.get_default_language
  * country pack summary  <- country_localization_service.resolve_country_pack
  * HONEST payment posture<- finance.country_readiness_register.assess_country
  * offline feature flags <- platform_runtime.offline_mode_bundle (booleans only)

The payment posture is the load-bearing honesty contract: a corridor that is a
placeholder stub (235/250 today) is reported with ``live_collection=False`` and
``data_state="placeholder"`` — the manifest NEVER tells an offline tenant that a
placeholder corridor can collect money. That is enforced for all time by
scripts/verify_regional_payment_profiles_honesty.py.

Pure-ish: reads model attributes + the registries above. No DB writes, no secrets.
Wrapped by callers in try/except so a resolution failure never breaks provisioning.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.sync_engine.tenant_manifest_compiler import TenantManifest, compile_manifest

logger = logging.getLogger(__name__)

# Offline routes the edge/PWA layer is allowed to serve from cache. Kept here (not
# in the compiler) because it is product policy, not a manifest primitive.
_OFFLINE_ROUTES_ALLOWLIST = (
    "/health/",
    "/offline/",
    "/portal/offline/",
)


def _country_code_for_school(school: Any) -> str:
    """Resolve an ISO-2 country code from a school via the canonical property when
    present, falling back to the raw attribute. Empty string when unknown."""
    cc = ""
    getter = getattr(school, "canonical_country_code", None)
    if isinstance(getter, str):
        cc = getter
    elif getter is not None and not callable(getter):
        cc = str(getter)
    if not cc:
        cc = str(getattr(school, "country_code", "") or "")
    return cc.strip().upper()[:2]


def _payment_posture(country_code: str) -> dict[str, Any]:
    """HONEST per-country payment posture for the offline manifest.

    A placeholder corridor (no researched rails/currency) reports live_collection
    False and data_state "placeholder" — it can never appear collectable offline.
    Resolution failures degrade to "unknown", never to an optimistic default."""
    posture: dict[str, Any] = {
        "country_code": country_code,
        "live_collection": False,
        "data_state": "unknown",
        "readiness_tier": "unknown",
        "currency": "",
        "tenant_action": "",
    }
    if not country_code:
        return posture
    try:
        from apps.finance.country_readiness_register import (
            TIER_CONFIG_ONLY,
            assess_country,
        )

        row = assess_country(country_code)
    except Exception:  # noqa: BLE001 - register is optional context; never break the manifest
        logger.debug("country_readiness assess failed for %s", country_code, exc_info=True)
        return posture
    if not row:
        return posture
    data_state = str(row.get("data_state") or "unknown")
    tier = str(row.get("overall_tier") or "unknown")
    # live_collection is true ONLY for a defined corridor whose adapter is live
    # (config_only). Placeholder corridors are forced false regardless of tier.
    live = data_state == "defined" and tier == TIER_CONFIG_ONLY
    posture.update(
        {
            "live_collection": bool(live),
            "data_state": data_state,
            "readiness_tier": tier,
            "currency": str(row.get("currency") or ""),
            "tenant_action": str(row.get("tenant_action") or ""),
        }
    )
    return posture


def _country_summary(country_code: str) -> dict[str, Any]:
    """Compact, offline-safe slice of the country pack (no heavy nested data)."""
    summary: dict[str, Any] = {"country_code": country_code, "resolved": False}
    if not country_code:
        return summary
    try:
        from apps.siteconfig.country_localization_service import (
            get_default_calendar_code,
            resolve_country_pack,
        )

        pack = resolve_country_pack(country_code)
        summary.update(
            {
                "resolved": True,
                "default_calendar": get_default_calendar_code(country_code),
                "school_type_count": len(pack.get("school_types") or []),
                "language_count": len(pack.get("languages") or []),
            }
        )
    except Exception:  # noqa: BLE001 - localization registry is optional context
        logger.debug("country pack resolve failed for %s", country_code, exc_info=True)
    return summary


def _offline_feature_flags() -> dict[str, bool]:
    """Boolean-only offline capability flags drawn from the offline-mode bundle SOT."""
    try:
        from apps.platform_runtime.offline_mode_bundle import (
            OFFLINE_MODE_BACKEND_FLAG_UPDATES,
        )

        return {
            k: bool(v)
            for k, v in OFFLINE_MODE_BACKEND_FLAG_UPDATES.items()
            if isinstance(v, bool)
        }
    except Exception:  # noqa: BLE001 - bundle module is the SOT; degrade to empty
        logger.debug("offline bundle flags unavailable", exc_info=True)
        return {}


def build_school_offline_manifest(school: Any) -> TenantManifest:
    """Compile an offline-sync manifest for ``school`` enriched with country context.

    This is the production entry point that connects the country profile to the
    offline manifest. Returns a deterministic, scrubbed :class:`TenantManifest`.
    """
    tenant_id = str(
        getattr(school, "schema_name", None)
        or getattr(school, "id", None)
        or getattr(school, "pk", None)
        or ""
    )
    if not tenant_id:
        # compile_manifest rejects an empty tenant id; surface the same contract.
        from apps.sync_engine.tenant_manifest_compiler import TenantManifestError

        raise TenantManifestError("school has no schema_name / id to scope a manifest")

    country_code = _country_code_for_school(school)
    locale_default = "en"
    if country_code:
        try:
            from apps.siteconfig.country_localization_service import get_default_language

            locale_default = get_default_language(country_code) or "en"
        except Exception:  # noqa: BLE001 - localization registry is optional context
            logger.debug("default language resolve failed for %s", country_code, exc_info=True)
    locale_default = (
        locale_default
        or str(getattr(school, "default_language", "") or "")
        or "en"
    )

    data_policies: dict[str, Any] = {
        "country": _country_summary(country_code),
        "payment": _payment_posture(country_code),
    }

    return compile_manifest(
        tenant_id=tenant_id,
        routes_allowlist=list(_OFFLINE_ROUTES_ALLOWLIST),
        data_policies=data_policies,
        pwa_cache_hints={"offline_routes": list(_OFFLINE_ROUTES_ALLOWLIST)},
        locale_default=locale_default,
        feature_flags=_offline_feature_flags(),
    )


def school_offline_manifest_dict(school: Any) -> dict[str, Any]:
    """Convenience: the compiled manifest as a plain dict for persistence/serving."""
    return build_school_offline_manifest(school).to_dict()


__all__ = ["build_school_offline_manifest", "school_offline_manifest_dict"]
