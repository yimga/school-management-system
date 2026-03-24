"""
Phase 6 — canonical runtime snapshots for inspection and tooling.

Single read-model for: effective entitlements (hard registry), blueprint pack/bundle
versioning (compare/update detection), and marketplace install surface (compatibility ops).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_entitlement_registry_snapshot(
    school: Any,
    policy: Optional[Dict[str, Any]],
    entitlements: Any,
) -> Dict[str, Any]:
    """
    Hard entitlement registry: one dict merging policy entitlements, plan, and runtime step-6 output.
    """
    policy = policy or {}
    policy_ent = policy.get("entitlements")
    if not isinstance(policy_ent, dict):
        policy_ent = {}

    plan_info: Dict[str, Any] = {}
    if school is not None:
        plan = getattr(school, "plan", None)
        if plan is not None:
            plan_info = {
                "plan_id": getattr(plan, "id", None),
                "plan_code": getattr(plan, "code", None)
                or getattr(plan, "slug", None),
                "plan_name": getattr(plan, "name", None)
                or getattr(plan, "label", None),
            }

    mods: List[str] = (
        list(getattr(entitlements, "modules", []) or []) if entitlements else []
    )

    return {
        "registry_schema_version": 1,
        "effective_modules": mods,
        "caps": {
            "max_students": getattr(entitlements, "max_students", None)
            if entitlements
            else None,
            "max_api_calls": getattr(entitlements, "max_api_calls", None)
            if entitlements
            else None,
        },
        "gates": {
            "marketplace_allowed": getattr(entitlements, "marketplace_allowed", False)
            if entitlements
            else False,
            "sandbox_enabled": getattr(entitlements, "sandbox_enabled", False)
            if entitlements
            else False,
            "white_label_enabled": getattr(entitlements, "white_label_enabled", False)
            if entitlements
            else False,
        },
        "sources": {
            "policy_entitlements": policy_ent,
            "plan": plan_info or None,
        },
        "raw_runtime_entitlements": getattr(entitlements, "raw", {})
        if entitlements
        else {},
    }


def build_blueprint_lifecycle_snapshot(school: Any) -> Dict[str, Any]:
    """
    Blueprint pack version vs active PolicyBundle.applied_pack_version (update detection).
    Preview/sandbox flags come from runtime.route in inspector payload, not here.
    """
    if school is None:
        return {}
    tb = getattr(school, "tenant_blueprint", None)
    if tb is None:
        return {"linked": False}

    pack = getattr(tb, "applied_pack", None)
    bundle = getattr(tb, "active_bundle", None)
    updated_at = getattr(tb, "updated_at", None)
    out: Dict[str, Any] = {
        "linked": True,
        "tenant_blueprint_updated_at": updated_at.isoformat()
        if updated_at is not None and hasattr(updated_at, "isoformat")
        else None,
        "applied_pack": None,
        "active_policy_bundle": None,
        "pack_update_needed": False,
    }

    if pack is not None:
        out["applied_pack"] = {
            "id": getattr(pack, "id", None),
            "slug": getattr(pack, "slug", None),
            "version": getattr(pack, "version", None),
            "name": getattr(pack, "name", None),
        }

    if bundle is not None:
        out["active_policy_bundle"] = {
            "id": getattr(bundle, "id", None),
            "bundle_version": getattr(bundle, "version", None),
            "applied_pack_version": getattr(bundle, "applied_pack_version", None)
            or None,
            "blueprint_compatibility": getattr(bundle, "blueprint_compatibility", None)
            or [],
        }

    pv = getattr(pack, "version", None) if pack is not None else None
    bv = (
        getattr(bundle, "applied_pack_version", None) or ""
        if bundle is not None
        else ""
    )
    if pv is not None and str(bv).strip() != str(pv).strip():
        out["pack_update_needed"] = True

    return out


def build_marketplace_install_snapshot(runtime: Any) -> Dict[str, Any]:
    """Installed apps + scopes for operator compatibility / health views."""
    m = getattr(runtime, "marketplace", None)
    if m is None:
        return {"registry_schema_version": 1, "active_installation_count": 0, "apps": []}

    apps_raw = list(getattr(m, "installed_apps", []) or [])
    scopes = list(getattr(m, "granted_scopes", []) or [])
    apps: List[Dict[str, Any]] = []
    for a in apps_raw:
        if not isinstance(a, dict):
            continue
        apps.append(
            {
                "app_slug": a.get("app_slug"),
                "app_id": a.get("app_id"),
                "version": a.get("version"),
                "name": a.get("name"),
            }
        )

    return {
        "registry_schema_version": 1,
        "active_installation_count": len(apps),
        "granted_scope_count": len(scopes),
        "apps": apps,
    }
