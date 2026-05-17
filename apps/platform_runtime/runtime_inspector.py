"""
Runtime inspector (Phase 9): operator tooling to see effective blueprint, active packs,
active policies, entitlements, localization, integrations, and override sources.
Use for debugging and control-plane visibility; not for tenant-facing UI.
"""

from __future__ import annotations

from typing import Any, Dict

from django.db import DatabaseError
from django.db.models import Q

from .runtime_resolver import build_tenant_runtime
from .contracts import TenantRuntime
from .governor_limits import get_governor_usage_for_tenant
from .precedence import PRECEDENCE_ORDER, describe_precedence_chain
from .registry_snapshots import (
    build_blueprint_lifecycle_snapshot,
    build_entitlement_registry_snapshot,
    build_marketplace_install_snapshot,
)
from .exceptions import RuntimeResolutionError
from apps.tenancy.context import TenantContext


def _serialize_blueprint(bp: Any) -> Dict[str, Any]:
    if bp is None:
        return {}
    return {
        "id": getattr(bp, "id", None),
        "code": getattr(bp, "code", None),
        "family": getattr(bp, "family", None),
        "name": getattr(bp, "name", None),
    }


def _serialize_policy(policy: Any) -> Dict[str, Any]:
    if policy is None:
        return {}
    if hasattr(policy, "raw"):
        return (
            getattr(policy, "raw", {})
            if isinstance(getattr(policy, "raw"), dict)
            else {}
        )
    return policy if isinstance(policy, dict) else {}


def _serialize_entitlements(ent: Any) -> Dict[str, Any]:
    if ent is None:
        return {}
    if hasattr(ent, "modules"):
        return {"modules": list(getattr(ent, "modules", []))}
    return ent if isinstance(ent, dict) else {}


def _serialize_locale(locale: Any) -> Dict[str, Any]:
    if locale is None:
        return {}
    return {
        "language_code": getattr(locale, "language_code", None),
        "direction": getattr(locale, "direction", None),
        "terminology_pack": getattr(locale, "terminology_pack", None),
    }


def _serialize_integrations(integ: Any) -> Dict[str, Any]:
    if integ is None:
        return {}
    if hasattr(integ, "enabled_slugs"):
        return {"enabled_slugs": list(getattr(integ, "enabled_slugs", []))}
    return integ if isinstance(integ, dict) else {}


def inspect_runtime(runtime: TenantRuntime) -> Dict[str, Any]:
    """
    Produce a serializable inspector payload from a TenantRuntime.
    Shows effective blueprint, active packs, active policies, entitlements,
    localization, integrations, and override sources.
    """
    debug = runtime.debug or {}
    pol = getattr(runtime, "policy", None)
    pol_dict: Dict[str, Any] = pol if isinstance(pol, dict) else {}
    return {
        "precedence_chain": describe_precedence_chain(),
        "feature_flags_merge_order": [
            PRECEDENCE_ORDER[3],
            PRECEDENCE_ORDER[5],
            PRECEDENCE_ORDER[6],
        ],
        "effective_blueprint": _serialize_blueprint(runtime.blueprint),
        "active_packs": {
            "workflow": getattr(getattr(runtime, "workflows", None), "pack_code", None),
            "dashboard": getattr(
                getattr(runtime, "dashboards", None), "pack_code", None
            ),
            "policy": getattr(
                getattr(runtime, "policy_typed", None), "bundle_code", None
            )
            if runtime.policy_typed
            else None,
        },
        "active_policies": _serialize_policy(runtime.policy_typed or runtime.policy),
        "entitlements": _serialize_entitlements(runtime.entitlements),
        "localization": _serialize_locale(runtime.locale),
        "integrations": _serialize_integrations(runtime.integrations),
        "override_sources": {
            "applied_overrides": list(getattr(debug, "applied_overrides", [])),
            "source_blueprint_id": getattr(debug, "source_blueprint_id", None),
            "source_policy_bundle_id": getattr(debug, "source_policy_bundle_id", None),
            "compilation_trace": list(getattr(debug, "compilation_trace", [])),
            "compilation_timestamp": getattr(debug, "compilation_timestamp", None),
        },
        "source_summary": {
            "blueprint_id": getattr(debug, "source_blueprint_id", None),
            "policy_bundle_id": getattr(debug, "source_policy_bundle_id", None),
            "preview_mode": getattr(
                getattr(runtime, "route", None), "is_preview", False
            ),
            "sandbox_mode": getattr(
                getattr(runtime, "route", None), "is_sandbox", False
            ),
        },
        "route": {
            "surface": getattr(getattr(runtime, "route", None), "surface", None),
            "is_preview": getattr(getattr(runtime, "route", None), "is_preview", False),
            "is_sandbox": getattr(getattr(runtime, "route", None), "is_sandbox", False),
        },
        "tenant_id": runtime.tenant_ctx.tenant_id if runtime.tenant_ctx else None,
        "school_id": runtime.tenant_ctx.school_id if runtime.tenant_ctx else None,
        "primary_sector": getattr(
            getattr(runtime, "tenant", None), "primary_sector", None
        ),
        "entitlement_registry": build_entitlement_registry_snapshot(
            getattr(runtime, "_school", None),
            pol_dict,
            runtime.entitlements,
        ),
        "blueprint_lifecycle": build_blueprint_lifecycle_snapshot(
            getattr(runtime, "_school", None)
        ),
        "marketplace_install_registry": build_marketplace_install_snapshot(runtime),
    }


def get_runtime_inspection(request: Any) -> Dict[str, Any]:
    """
    Inspect runtime for the current request. Uses request.tenant_runtime if set,
    otherwise builds runtime for request (no cache). Returns serializable dict.
    """
    rt = getattr(request, "tenant_runtime", None)
    if rt is None:
        tenant_ctx = getattr(request, "tenant_ctx", None)
        if tenant_ctx is None:
            from apps.tenancy.middleware import build_tenant_context_from_request

            tenant_ctx = build_tenant_context_from_request(request)
        if tenant_ctx is None:
            return {
                "error": "no_tenant_context",
                "effective_blueprint": {},
                "override_sources": {},
                "governor_limits": get_governor_usage_for_tenant(),
                "feature_toggles": [],
            }
        school = getattr(request, "school", None) or getattr(
            getattr(request, "tenant", None), "school", None
        )
        try:
            rt = build_tenant_runtime(tenant_ctx, request=request, school=school)
        except (
            AttributeError,
            DatabaseError,
            RuntimeResolutionError,
            TypeError,
            ValueError,
        ) as e:
            return {
                "error": str(e),
                "effective_blueprint": {},
                "override_sources": {},
                "governor_limits": None,
                "feature_toggles": [],
            }
    out = inspect_runtime(rt)
    tid = rt.tenant_ctx.tenant_id if rt.tenant_ctx else None
    sid = rt.tenant_ctx.school_id if rt.tenant_ctx else None
    out["governor_limits"] = get_governor_usage_for_tenant(tenant_id=tid, school_id=sid)
    return out


def get_feature_toggle_inspection(school: Any) -> list:
    """
    Phase 10 — 10.2 / GAP.13: Active feature toggle overrides with registry metadata.
    Returns list of dicts: key, is_enabled, expires_at, source (school|global),
    owner, definition_source, scope (from FeatureToggleDefinition).
    """
    import logging
    from django.db import DatabaseError
    from django.utils import timezone

    logger = logging.getLogger(__name__)
    out = []
    try:
        from apps.policies_rules.models import FeatureToggleState

        now = timezone.now()
        q = (
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            FeatureToggleState.objects.filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now)
            )
            .select_related("definition")
            .order_by("definition__key")
        )

        def _row(state, override_source: str) -> Dict[str, Any]:
            defin = getattr(state, "definition", None)
            key = (
                getattr(defin, "key", None)
                if defin
                else (str(state.definition_id) if state.definition_id else "—")
            )
            return {
                "key": key,
                "is_enabled": state.is_enabled,
                "expires_at": state.expires_at.strftime("%Y-%m-%d %H:%M")
                if state.expires_at
                else None,
                "source": override_source,
                "owner": getattr(defin, "owner", None) or "",
                "definition_source": getattr(defin, "source", None) or "",
                "scope": getattr(defin, "scope", None) or "",
            }

        for state in q.filter(school=school):
            out.append(_row(state, "school"))
        for state in q.filter(school__isnull=True):
            out.append(_row(state, "global"))
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
        logger.warning(
            "feature_toggle_inspection_skipped school_id=%s error=%s",
            getattr(school, "id", None),
            e,
            exc_info=True,
        )
    return out


def _get_entitlements_why(school: Any, out: Dict[str, Any]) -> Dict[str, Any]:
    """
    GAP.6: Why these entitlements — which plan/rule/policy granted them.
    Returns dict with policy_bundle_id, blueprint_id, plan_name for UI.
    """
    why = {
        "policy_bundle_id": out.get("source_summary", {}).get("policy_bundle_id"),
        "blueprint_id": out.get("source_summary", {}).get("blueprint_id"),
        "plan_name": None,
        "plan_code": None,
    }
    if school:
        plan = getattr(school, "plan", None)
        if plan is not None:
            why["plan_name"] = getattr(plan, "name", None) or getattr(
                plan, "label", None
            )
            why["plan_code"] = getattr(plan, "code", None)
    return why


def get_runtime_inspection_for_school(school: Any) -> Dict[str, Any]:
    """
    Inspect runtime for a school (e.g. control-plane operator view). Builds runtime
    without a request; use for background or super views.
    """
    if school is None:
        return {
            "error": "no_school",
            "effective_blueprint": {},
            "override_sources": {},
            "governor_limits": get_governor_usage_for_tenant(),
        }
    tenant_ctx = TenantContext(
        tenant_id=str(getattr(school, "id", "")),
        schema_name=getattr(school, "schema_name", None),
        school_id=getattr(school, "id", None),
        country=getattr(school, "default_region_id", None)
        or getattr(school, "country", None),
        timezone=getattr(school, "timezone", None),
        feature_flags={},
        policy_overrides={},
        host="",
    )
    try:
        rt = build_tenant_runtime(tenant_ctx, request=None, school=school)
        out = inspect_runtime(rt)
        out["governor_limits"] = get_governor_usage_for_tenant(
            tenant_id=str(getattr(school, "id", "")),
            school_id=getattr(school, "id", None),
        )
        # Phase 10 — 10.2: why this feature is on (toggle state + expiry)
        out["feature_toggles"] = get_feature_toggle_inspection(school)
        # GAP.6: why these entitlements (which plan/rule/policy enabled them)
        out["entitlements_why"] = _get_entitlements_why(school, out)
        return out
    except (
        AttributeError,
        DatabaseError,
        RuntimeResolutionError,
        TypeError,
        ValueError,
    ) as e:
        return {
            "error": str(e),
            "effective_blueprint": {},
            "override_sources": {},
            "governor_limits": None,
            "feature_toggles": [],
        }
