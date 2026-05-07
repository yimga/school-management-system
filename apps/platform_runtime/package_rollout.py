"""Commercial package rollout contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def package_diff(current: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    current_modules = set(current.get("modules", []))
    target_modules = set(target.get("modules", []))
    current_limits = current.get("limits", {}) or {}
    target_limits = target.get("limits", {}) or {}
    return {
        "current_version": current.get("version", ""),
        "target_version": target.get("version", ""),
        "modules_added": sorted(target_modules - current_modules),
        "modules_removed": sorted(current_modules - target_modules),
        "limits_changed": {
            key: {"from": current_limits.get(key), "to": target_limits.get(key)}
            for key in sorted(set(current_limits) | set(target_limits))
            if current_limits.get(key) != target_limits.get(key)
        },
        "support_level_changed": current.get("support_level") != target.get("support_level"),
        "offline_eligibility_changed": current.get("offline_eligible") != target.get("offline_eligible"),
        "api_access_changed": current.get("api_access") != target.get("api_access"),
        "automation_access_changed": current.get("automation_access") != target.get("automation_access"),
        "analytics_access_changed": current.get("analytics_access") != target.get("analytics_access"),
    }


def billing_impact_preview(current: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    current_price = Decimal(str(current.get("price", "0")))
    target_price = Decimal(str(target.get("price", "0")))
    psp_verified = bool(target.get("psp_live_verified") and target.get("psp_evidence_path"))
    return {
        "current_price": str(current_price),
        "projected_price": str(target_price),
        "delta": str(target_price - current_price),
        "manual_fallback": not psp_verified,
        "external_psp_state": "live_verified" if psp_verified else "external_required",
        "charge_permitted": psp_verified,
    }


def package_change_request(current: dict[str, Any], target: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
    diff = package_diff(current, target)
    impact = billing_impact_preview(current, target)
    downgrade = bool(diff["modules_removed"] or any(
        change["to"] is not None and change["from"] is not None and change["to"] < change["from"]
        for change in diff["limits_changed"].values()
        if isinstance(change["from"], (int, float)) and isinstance(change["to"], (int, float))
    ))
    return {
        "tenant_id": tenant_id,
        "preview_required": True,
        "approval_required": True,
        "effective_date_required": True,
        "package_diff": diff,
        "billing_impact": impact,
        "downgrade": downgrade,
        "downgrade_posture": "explain_lost_features_and_data_impact" if downgrade else "not_applicable",
        "auditable": True,
    }
