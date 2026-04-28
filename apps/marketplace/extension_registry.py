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

