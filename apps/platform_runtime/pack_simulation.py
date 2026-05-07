"""Pack simulation engine."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from apps.platform_runtime.pack_audit import audit_pack_event
from apps.platform_runtime.pack_contract import get_pack_or_raise


def _simulation_id(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def simulate_pack(
    pack_key: str,
    *,
    pack_type: str | None = None,
    school=None,
    actor=None,
    scenario: str = "standard",
    platform_operator: bool = False,
    emit_audit: bool = False,
) -> dict[str, Any]:
    pack = get_pack_or_raise(pack_key, pack_type=pack_type)
    blocked = []
    if school is None and pack.tenant_scope == "tenant":
        blocked.append("tenant_required")
    if pack.platform_only and not platform_operator:
        blocked.append("platform_operator_required")
    result: dict[str, Any] = {
        "pack_key": pack.key,
        "pack_type": pack.pack_type,
        "scenario": scenario,
        "result": "blocked" if blocked else "simulated",
        "actions_that_would_run": [],
        "warnings": list(pack.external_dependencies),
        "blocked_reasons": blocked,
        "audit_summary": {
            "events": ["pack_simulated", "pack_apply_requested", "pack_applied"],
            "would_emit": ["pack_simulated"],
        },
    }
    if pack.pack_type == "workflow_pack":
        result.update(
            {
                "trigger_event": pack.triggers[0] if pack.triggers else "manual",
                "conditions_evaluated": list(pack.conditions),
                "actions_that_would_run": list(pack.actions),
                "messages": list(pack.message_templates),
                "escalations": list(pack.escalation_rules),
            }
        )
    elif pack.pack_type == "dashboard_pack":
        result.update(
            {
                "layout": pack.layout,
                "widgets": list(pack.widgets),
                "cards": list(pack.widgets),
                "actions_that_would_run": list(pack.dashboard_actions),
                "empty_states": list(pack.empty_states),
                "permission_visibility": {role: list(pack.widgets) for role in pack.target_roles},
                "mobile_behavior": pack.mobile_behavior,
            }
        )
    else:
        result.update(
            {
                "decision": "requires_approval" if pack.approval_flows else "allowed",
                "rules_evaluated": list(pack.rules),
                "approval_flows": list(pack.approval_flows),
                "affected_roles": list(pack.target_roles),
                "audit_requirements": list(pack.audit_requirements),
            }
        )
    result["simulation_id"] = _simulation_id(result)
    if emit_audit:
        event = audit_pack_event(
            "pack_simulated",
            pack_key=pack.key,
            pack_type=pack.pack_type,
            school=school,
            actor=actor,
            result=result["result"],
            payload={"scenario": scenario, "simulation_id": result["simulation_id"]},
        )
        if event:
            result["audit_id"] = event.pk
    return result
