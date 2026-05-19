"""
Marketplace extension registry.

Single source for extension points that third-party packs/apps can target.
"""

from __future__ import annotations

from typing import Any


EXTENSION_POINTS: dict[str, dict[str, Any]] = {
    "workflow_hooks": {
        "surface": "apps.automation",
        "description": "Pre/post execution workflow hooks for approved playbooks.",
        "required_manifest_fields": ["hook_name", "event_types"],
    },
    "dashboard_cards": {
        "surface": "apps.schools.super_views_command_center_views",
        "description": "Operator cards rendered on founder/command-center dashboards.",
        "required_manifest_fields": ["card_id", "title", "template_ref"],
    },
    "billing_entitlements": {
        "surface": "apps.billing.services",
        "description": "Entitlement and pricing overlays for marketplace packs.",
        "required_manifest_fields": ["entitlement_code", "tier"],
    },
    "event_webhooks": {
        "surface": "apps.platform_runtime.events",
        "description": "Outbound event subscriptions for integration partners.",
        "required_manifest_fields": ["event_type", "target_url"],
    },
}


def get_extension_registry() -> dict[str, dict[str, Any]]:
    return dict(EXTENSION_POINTS)


def validate_extension_manifest(
    manifest: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    """
    Validate a third-party extension manifest against EXTENSION_POINTS (Linux pillar).

    Returns ``(ok, errors)``. Does not assert third-party certification.
    """
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return False, ["manifest must be a JSON object"]

    ext_point = str(manifest.get("extension_point") or "").strip()
    if not ext_point:
        errors.append("extension_point is required")
        return False, errors

    spec = EXTENSION_POINTS.get(ext_point)
    if spec is None:
        known = ", ".join(sorted(EXTENSION_POINTS))
        errors.append(f"unknown extension_point {ext_point!r}; known: {known}")
        return False, errors

    for field in spec.get("required_manifest_fields") or []:
        val = manifest.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(f"missing required field {field!r}")

    hook = str(manifest.get("hook_name") or manifest.get("card_id") or "").strip()
    if ext_point == "workflow_hooks" and hook and len(hook) > 64:
        errors.append("hook_name exceeds 64 characters")

    return len(errors) == 0, errors


def validate_marketplace_app_manifest(
    manifest: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    """
    Validate ``MarketplaceApp.manifest`` extension hook declarations.

    Accepts a single hook dict under ``extension_hook`` / ``extension`` or a list
    under ``extension_hooks`` / ``extensions``.
    """
    if not manifest:
        return True, []
    if not isinstance(manifest, dict):
        return False, ["manifest must be a JSON object"]

    errors: list[str] = []
    singles = (
        manifest.get("extension_hook"),
        manifest.get("extension"),
    )
    for item in singles:
        if isinstance(item, dict):
            ok, errs = validate_extension_manifest(item)
            if not ok:
                errors.extend(errs)

    for key in ("extension_hooks", "extensions"):
        hooks = manifest.get(key)
        if hooks is None:
            continue
        if not isinstance(hooks, list):
            errors.append(f"{key} must be a list of extension manifests")
            continue
        for idx, hook in enumerate(hooks):
            if not isinstance(hook, dict):
                errors.append(f"{key}[{idx}] must be an object")
                continue
            ok, errs = validate_extension_manifest(hook)
            if not ok:
                errors.extend([f"{key}[{idx}]: {e}" for e in errs])

    return len(errors) == 0, errors


__all__ = [
    "EXTENSION_POINTS",
    "get_extension_registry",
    "validate_extension_manifest",
    "validate_marketplace_app_manifest",
]

