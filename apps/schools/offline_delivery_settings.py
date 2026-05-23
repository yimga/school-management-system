"""School.settings[\"offline_delivery\"] bridge (SODP batch 1406)."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.offline_action_types import OfflineActionType

_DEFAULT_MAX_QUEUE = 500
_DEFAULT_PROFILE = "standard"


def get_offline_delivery_payload(school) -> dict[str, Any]:
    """Normalized offline delivery settings for a tenant."""
    raw: dict[str, Any] = {}
    if school is not None:
        settings_json = getattr(school, "settings", None) or {}
        if isinstance(settings_json, dict):
            raw = settings_json.get("offline_delivery") or {}
    hub_url = (raw.get("hub_base_url") or raw.get("hub_url") or "").strip()
    try:
        max_queue = int(raw.get("max_queue_items") or _DEFAULT_MAX_QUEUE)
    except (TypeError, ValueError):
        max_queue = _DEFAULT_MAX_QUEUE
    max_queue = max(50, min(max_queue, 5000))
    allowed = raw.get("allowed_action_types") or []
    if not isinstance(allowed, list):
        allowed = []
    allowed_norm = [
        str(x).strip()
        for x in allowed
        if str(x).strip() in OfflineActionType.values
    ]
    return {
        "hub_base_url": hub_url,
        "mesh_enabled": bool(raw.get("mesh_enabled")),
        "max_queue_items": max_queue,
        "profile_hint": (raw.get("profile_hint") or _DEFAULT_PROFILE).strip()[:32],
        "allowed_action_types": allowed_norm or list(OfflineActionType.values),
    }


def set_offline_delivery_payload(school, payload: dict[str, Any]) -> None:
    """Persist offline_delivery into School.settings (does not save)."""
    if not isinstance(school.settings, dict):
        school.settings = {}
    current = get_offline_delivery_payload(school)
    hub = (payload.get("hub_base_url") or payload.get("hub_url") or current["hub_base_url"]).strip()
    try:
        max_queue = int(payload.get("max_queue_items", current["max_queue_items"]))
    except (TypeError, ValueError):
        max_queue = current["max_queue_items"]
    max_queue = max(50, min(max_queue, 5000))
    allowed = payload.get("allowed_action_types")
    if allowed is None:
        allowed = current["allowed_action_types"]
    if not isinstance(allowed, list):
        allowed = current["allowed_action_types"]
    school.settings["offline_delivery"] = {
        "hub_base_url": hub,
        "mesh_enabled": bool(payload.get("mesh_enabled", current["mesh_enabled"])),
        "max_queue_items": max_queue,
        "profile_hint": (payload.get("profile_hint") or current["profile_hint"]).strip()[:32],
        "allowed_action_types": [
            str(x).strip()
            for x in allowed
            if str(x).strip() in OfflineActionType.values
        ],
    }


def build_client_offline_config(
    school,
    *,
    deployment_profile: str = "online",
    feature_flags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge tenant JSON + feature flags for SMS_OFFLINE_CONFIG."""
    payload = get_offline_delivery_payload(school)
    flags = feature_flags or {}
    hub = payload["hub_base_url"] or (flags.get("hub_base_url") or "")
    return {
        "maxQueueItems": payload["max_queue_items"],
        "hubBaseUrl": hub,
        "meshEnabled": payload["mesh_enabled"],
        "profileHint": payload["profile_hint"],
        "allowedActionTypes": payload["allowed_action_types"],
        "deploymentProfile": (deployment_profile or "online").strip().lower(),
    }


__all__ = [
    "build_client_offline_config",
    "get_offline_delivery_payload",
    "set_offline_delivery_payload",
]
