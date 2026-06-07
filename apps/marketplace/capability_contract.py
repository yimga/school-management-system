"""
Wave 1 — Marketplace app capability contract.

Every first-party catalog app must declare how install/activate changes tenant runtime
(feature flags, packages, integration adapters, widgets, or extension hooks).
"""

from __future__ import annotations

import re
from typing import Any

VALID_BINDING_KINDS = frozenset(
    {
        "feature",
        "package_id",
        "widget",
        "extension_hook",
        "integration_adapter",
        "workflow_trigger",
    }
)

# Wave 3 — priority apps with richer bindings (features + widgets where applicable).
TOP_15_APP_SLUGS = frozenset(
    {
        "billing-fees-pack",
        "parent-engagement-pack",
        "transport-bus-tracker",
        "cafeteria-meal-plans",
        "sso-identity",
        "sis-bridge-oneroster-v1p2",
        "messaging-sms-gateway",
        "payments-paystack",
        "payments-flutterwave-momo",
        "advanced-workflow-builder",
        "compliance-export",
        "student-360-pack",
        "onboarding-wizard-pack",
        "api-webhooks-pack",
        "analytics-insights-pack",
    }
)

_SLUG_FEATURE_MAP: dict[str, list[str]] = {
    "transport-bus-tracker": ["transport"],
    "transport-route-optimizer": ["transport"],
    "cafeteria-meal-plans": ["canteen"],
    "library-asset-tracker": ["library"],
    "medical-clinic-records": ["clinic"],
    "boarding-house-management": ["dormitory"],
    "timetable-scheduling-pro": ["timetabling"],
    "parent-engagement-pack": ["parent_chat"],
    "iot-biometric-attendance": ["offline_mode"],
    "iot-rfid-asset-tracking": ["inventory"],
    "alumni-engagement-pack": ["alumni"],
    "alumni-development-fundraising": ["alumni"],
    "specialty-after-school-program": ["visitor_log"],
    "procurement-vendor-management": ["inventory"],
}


def _integration_adapter_target(slug: str) -> str | None:
    if slug.startswith("sis-bridge-"):
        return f"sis:{slug.removeprefix('sis-bridge-')}"
    if slug.startswith("lms-bridge-"):
        return f"lms:{slug.removeprefix('lms-bridge-')}"
    if slug.startswith("payments-"):
        return f"payments:{slug.removeprefix('payments-')}"
    if slug.startswith("messaging-"):
        return f"messaging:{slug.removeprefix('messaging-')}"
    if slug.startswith("identity-"):
        return f"identity:{slug.removeprefix('identity-')}"
    if slug in ("sso-identity", "migration-connector-pack", "api-webhooks-pack"):
        return f"platform:{slug}"
    return None


def _widget_bindings_for_top_app(slug: str) -> list[dict[str, str]]:
    """Widget capability bindings from sandbox embed registry (TOP_15)."""
    from apps.marketplace.sandbox_embed_registry import registry_specs_for_slug

    return [
        {"kind": "widget", "target": spec.widget_id, "mode": "register_on_activate"}
        for spec in registry_specs_for_slug(slug)
    ]


def infer_capability_bindings(slug: str, manifest: dict[str, Any] | None) -> list[dict[str, str]]:
    """
    Derive capability_bindings for a catalog app slug (idempotent; used by seed + verifier).
    """
    manifest = manifest if isinstance(manifest, dict) else {}
    slug = (slug or "").strip()
    bindings: list[dict[str, str]] = []

    for feat in _SLUG_FEATURE_MAP.get(slug, []):
        code = str(feat).strip()
        if code:
            bindings.append(
                {"kind": "feature", "target": code, "mode": "enable_on_activate"}
            )

    adapter = _integration_adapter_target(slug)
    if adapter:
        bindings.append(
            {
                "kind": "integration_adapter",
                "target": adapter,
                "mode": "surface_on_activate",
            }
        )

    if slug in TOP_15_APP_SLUGS:
        pkg = (manifest.get("package_id") or slug).strip()
        if pkg and not any(b.get("kind") == "package_id" for b in bindings):
            bindings.append(
                {"kind": "package_id", "target": pkg, "mode": "apply_on_activate"}
            )
        bindings.extend(_widget_bindings_for_top_app(slug))

    if manifest.get("extension_hook") or manifest.get("extension_hooks"):
        bindings.append(
            {
                "kind": "extension_hook",
                "target": slug,
                "mode": "register_on_activate",
            }
        )

    if slug == "advanced-workflow-builder":
        bindings.append(
            {
                "kind": "workflow_trigger",
                "target": "app_installed",
                "mode": "dispatch_on_activate",
            }
        )

    if not bindings:
        pkg = (manifest.get("package_id") or slug).strip()
        bindings.append(
            {"kind": "package_id", "target": pkg, "mode": "apply_on_activate"}
        )

    # De-duplicate by (kind, target)
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for b in bindings:
        kind = str(b.get("kind") or "").strip()
        target = str(b.get("target") or "").strip()
        key = (kind, target)
        if not kind or not target or key in seen:
            continue
        seen.add(key)
        deduped.append({"kind": kind, "target": target, "mode": str(b.get("mode") or "")})
    return deduped


def extract_capability_bindings(manifest: dict[str, Any] | None) -> list[dict[str, str]]:
    manifest = manifest if isinstance(manifest, dict) else {}
    raw = manifest.get("capability_bindings")
    if isinstance(raw, list) and raw:
        out: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip()
            target = str(item.get("target") or "").strip()
            if kind and target:
                out.append(
                    {
                        "kind": kind,
                        "target": target,
                        "mode": str(item.get("mode") or "").strip(),
                    }
                )
        if out:
            return out
    # Legacy: widgets dict, package_id, enabled_features
    legacy: list[dict[str, str]] = []
    pkg = str(manifest.get("package_id") or "").strip()
    if pkg:
        legacy.append(
            {"kind": "package_id", "target": pkg, "mode": "apply_on_activate"}
        )
    widgets = manifest.get("widgets")
    if isinstance(widgets, dict):
        for w_id in widgets:
            wid = str(w_id).strip()
            if wid:
                legacy.append(
                    {"kind": "widget", "target": wid, "mode": "register_on_activate"}
                )
    for feat in manifest.get("enabled_features") or []:
        code = str(feat).strip()
        if code:
            legacy.append(
                {"kind": "feature", "target": code, "mode": "enable_on_activate"}
            )
    return legacy


def manifest_has_capability_contract(manifest: dict[str, Any] | None) -> bool:
    return len(extract_capability_bindings(manifest)) > 0


def validate_capability_bindings(manifest: dict[str, Any] | None) -> tuple[bool, list[str]]:
    errors: list[str] = []
    bindings = extract_capability_bindings(manifest)
    if not bindings:
        errors.append("capability_bindings missing or empty")
        return False, errors
    for idx, b in enumerate(bindings):
        kind = str(b.get("kind") or "").strip()
        target = str(b.get("target") or "").strip()
        if kind not in VALID_BINDING_KINDS:
            errors.append(f"binding[{idx}]: invalid kind {kind!r}")
        if not target:
            errors.append(f"binding[{idx}]: empty target")
        elif len(target) > 120:
            errors.append(f"binding[{idx}]: target exceeds 120 chars")
        elif kind == "feature" and not re.match(r"^[a-z][a-z0-9_]*$", target):
            errors.append(f"binding[{idx}]: feature target {target!r} invalid")
    return len(errors) == 0, errors


def enrich_manifest_capability_bindings(
    slug: str, manifest: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge inferred capability_bindings into manifest (non-destructive)."""
    base = dict(manifest) if isinstance(manifest, dict) else {}
    existing = extract_capability_bindings(base)
    if existing:
        base["capability_bindings"] = existing
        return base
    inferred = infer_capability_bindings(slug, base)
    base["capability_bindings"] = inferred
    # Wave 3: mirror feature bindings into enabled_features for entitlement hints
    feats = [
        b["target"]
        for b in inferred
        if b.get("kind") == "feature" and b.get("target")
    ]
    if feats:
        merged_feats = list(dict.fromkeys(list(base.get("enabled_features") or []) + feats))
        base["enabled_features"] = merged_feats
    if slug in TOP_15_APP_SLUGS and not base.get("package_id"):
        base["package_id"] = slug
    from apps.marketplace.sandbox_embed_registry import merge_sandbox_widgets_into_manifest

    base = merge_sandbox_widgets_into_manifest(slug, base)
    return base


def capability_summary(manifest: dict[str, Any] | None) -> dict[str, Any]:
    bindings = extract_capability_bindings(manifest)
    by_kind: dict[str, list[str]] = {}
    for b in bindings:
        kind = b.get("kind") or "unknown"
        by_kind.setdefault(kind, []).append(b.get("target") or "")
    return {
        "binding_count": len(bindings),
        "kinds": sorted(by_kind.keys()),
        "by_kind": by_kind,
    }
