"""Blueprint impact analysis."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.blueprint_audit import audit_blueprint_event
from apps.platform_runtime.blueprint_preview import preview_blueprint


def analyze_blueprint_impact(
    blueprint_key: str,
    *,
    school=None,
    actor=None,
    platform_operator: bool = False,
    emit_audit: bool = False,
) -> dict[str, Any]:
    preview = preview_blueprint(
        blueprint_key,
        school=school,
        actor=actor,
        platform_operator=platform_operator,
        emit_audit=False,
    )
    destructive_changes = [
        row for row in preview["changes"] if row.get("destructive")
    ]
    external_required = list(preview.get("external_required") or [])
    categories: list[str] = []
    if preview.get("conflicts"):
        categories.append("tenant_blocked")
    if external_required:
        categories.append("external_required")
    offline_readiness = preview.get("offline_readiness", {})
    # Offline proof only — a live-payment gate is already carried by the
    # "external_required" category above and is not an offline-proof shortfall.
    if offline_readiness.get("status") == "PARTIAL":
        categories.append("offline_proof_partial")
    if destructive_changes:
        categories.append("destructive")
    if len(preview["changes"]) >= 20:
        categories.append("high")
    elif len(preview["changes"]) >= 10:
        categories.append("medium")
    else:
        categories.append("low")
    if "platform_operator_required" in {
        conflict.get("code") for conflict in preview.get("conflicts", [])
    }:
        categories.append("platform_only")

    result = {
        "blueprint_key": preview["blueprint_key"],
        "tenant": preview["tenant"],
        "impact_categories": list(dict.fromkeys(categories)),
        "summary": {
            "what_changes": [row["target"] for row in preview["changes"]],
            "who_is_affected": sorted(
                {
                    row["target"]
                    for row in preview["changes"]
                    if row["section"] in {"role", "permission"}
                }
            ),
            "roles_gain_access": [
                row["target"] for row in preview["changes"] if row["section"] == "role"
            ],
            "workflows_activate": [
                row["target"]
                for row in preview["changes"]
                if row["section"] == "workflow_pack"
            ],
            "dashboards_change": [
                row["target"]
                for row in preview["changes"]
                if row["section"] == "dashboard_pack"
            ],
            "policies_active": [
                row["target"]
                for row in preview["changes"]
                if row["section"] == "policy_bundle"
            ],
            "billing_package_rules": [
                row["target"]
                for row in preview["changes"]
                if row["section"] == "billing_defaults"
            ],
            "external_dependencies_remaining": external_required,
            "offline_readiness": offline_readiness,
            "local_first_manifest": preview.get("local_first_manifest", {}),
            "outage_survival_matrix": preview.get("outage_survival_matrix", {}),
            "conflict_policy_by_domain": preview.get("conflict_policy_by_domain", {}),
            "rollback_available": preview["rollback_plan"]["available"],
            "cannot_rollback": preview["rollback_plan"]["non_reversible"],
        },
        "requires_confirmation": preview["requires_confirmation"]
        or bool(destructive_changes)
        or "medium" in categories
        or "high" in categories,
        "can_apply": preview["can_apply"],
        "conflicts": preview["conflicts"],
        "warnings": preview["warnings"],
    }
    if emit_audit:
        event = audit_blueprint_event(
            "blueprint_impact_viewed",
            blueprint_key=preview["blueprint_key"],
            school=school,
            actor=actor,
            result="blocked" if result["conflicts"] else "ok",
            payload={"impact_categories": result["impact_categories"]},
        )
        if event:
            result["audit_id"] = event.pk
    return result
