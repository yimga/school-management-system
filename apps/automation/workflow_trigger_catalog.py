"""
Canonical domain trigger hints for Studio OS + visual workflow simulation.

Maps high-level trigger keys (aligned with ``Workflow.Trigger``) to operator-facing
labels, sample payloads, and supported condition/action families.
"""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings


def _sim_currency() -> str:
    """Currency for simulated trigger payloads.

    Reads `settings.PLATFORM_DEFAULT_CURRENCY` (env-overridable) so the
    workflow simulator shows the operator's local currency, not a hardcoded
    XAF leftover from the original Cameroon-focused build.
    """
    return getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD")

# Narrow slice proven in ``test_workflow_studio_closure_slice`` (Section 11.4 workflow_engine).
CLOSURE_SLICE_TRIGGER_KEYS: tuple[str, str, str] = (
    "attendance_saved",
    "payment_success",
    "report_generated",
)

# Full operator catalog (batch 1147+): Studio simulation + designer parity.
FULL_TRIGGER_CATALOG_KEYS: tuple[str, ...] = (
    "attendance_saved",
    "payment_success",
    "payment_failed",
    "report_generated",
    "marks_submitted",
    "student_risk_detected",
    "app_installed",
    "offline_action_conflict",
)

_TRIGGER_META: dict[str, dict[str, Any]] = {
    "attendance_saved": {
        "label": "Attendance saved (platform)",
        "supported_conditions": [
            "Equality / comparison on payload fields (e.g. school_id, saved_count)",
            "Time windows via date_* / hour_between when payload includes timestamps",
        ],
        "supported_actions": [
            "notify (log/parent)",
            "emit_event",
            "webhook (preview only under dry-run)",
        ],
    },
    "payment_success": {
        "label": "Payment succeeded",
        "supported_conditions": [
            "Thresholds on amount_cents",
            "currency eq / in list",
        ],
        "supported_actions": [
            "notify",
            "create_record / update_field",
            "emit_event",
        ],
    },
    "payment_failed": {
        "label": "Payment failed",
        "supported_conditions": [
            "invoice_id present",
            "failure_reason eq / contains",
            "retry_count thresholds",
        ],
        "supported_actions": [
            "notify",
            "emit_event",
            "create_record (escalation ticket stub)",
        ],
    },
    "report_generated": {
        "label": "Report generated",
        "supported_conditions": [
            "report_type eq / in",
            "report_id present (non-empty)",
        ],
        "supported_actions": [
            "notify",
            "emit_event",
            "webhook (preview)",
        ],
    },
    "marks_submitted": {
        "label": "Marks submitted",
        "supported_conditions": [
            "classroom_id / subject_id filters",
            "submitted_by role checks when present in payload",
        ],
        "supported_actions": [
            "notify",
            "emit_event",
            "create_record",
        ],
    },
    "student_risk_detected": {
        "label": "Student risk detected",
        "supported_conditions": [
            "risk_score thresholds",
            "risk_tier eq / in list",
        ],
        "supported_actions": [
            "notify",
            "emit_event",
            "create_record",
        ],
    },
    "app_installed": {
        "label": "Marketplace app installed",
        "supported_conditions": [
            "app_slug / installation_id present",
            "plan tier comparison when payload includes it",
        ],
        "supported_actions": [
            "notify",
            "emit_event",
        ],
    },
    "offline_action_conflict": {
        "label": "Offline sync action conflict",
        "supported_conditions": [
            "conflict_entity_type eq",
            "device_id present",
        ],
        "supported_actions": [
            "notify",
            "emit_event",
            "create_record",
        ],
    },
}


def sample_payload_for_trigger(school_id: str, trigger_key: str) -> dict[str, Any]:
    """Deterministic sample context for simulate / dispatch-test APIs and docs."""
    base = {"school_id": school_id}
    if trigger_key == "attendance_saved":
        return {
            **base,
            "session_id": "sim-session-001",
            "saved_count": 1,
            "student_id": "stu-sim-001",
        }
    if trigger_key == "payment_success":
        return {
            **base,
            "invoice_id": "inv-sim-001",
            "amount_cents": 2500,
            "currency": _sim_currency(),
        }
    if trigger_key == "payment_failed":
        return {
            **base,
            "invoice_id": "inv-sim-fail-001",
            "amount_cents": 2500,
            "currency": _sim_currency(),
            "failure_reason": "card_declined",
            "retry_count": 2,
        }
    if trigger_key == "report_generated":
        return {
            **base,
            "report_id": "rpt-sim-001",
            "report_type": "term_summary",
        }
    if trigger_key == "marks_submitted":
        return {
            **base,
            "classroom_id": "cls-sim-001",
            "subject_id": "subj-sim-001",
            "submitted_by": "teacher-1",
            "term_position": 1,
        }
    if trigger_key == "student_risk_detected":
        return {
            **base,
            "student_id": "stu-risk-001",
            "risk_score": 0.82,
            "risk_tier": "high",
            "signals": ["attendance", "grades"],
        }
    if trigger_key == "app_installed":
        return {
            **base,
            "installation_id": "inst-sim-001",
            "app_slug": "grade-sync-demo",
            "marketplace_app_id": "42",
        }
    if trigger_key == "offline_action_conflict":
        return {
            **base,
            "conflict_entity_type": "grade_entry",
            "local_record_id": "local-777",
            "server_record_id": "srv-888",
            "device_id": "device-tablet-01",
        }
    return dict(base)


_SIM_HINT = (
    "POST /automation/workflows/api/simulate/ with workflow_id + "
    "sample_payload (dry-run; no WorkflowRunLog row). "
    "dispatch-test runs matching published workflows with dry_run=true."
)


def get_operator_trigger_catalog_for_school(
    school_id: str,
    *,
    slice_only: bool = True,
) -> list[dict[str, Any]]:
    """Rows for Studio templates: label, payloads, condition/action hints."""
    keys = CLOSURE_SLICE_TRIGGER_KEYS if slice_only else FULL_TRIGGER_CATALOG_KEYS
    rows: list[dict[str, Any]] = []
    for key in keys:
        m = _TRIGGER_META.get(key)
        if not m:
            continue
        sample = sample_payload_for_trigger(school_id, key)
        rows.append(
            {
                "trigger_key": key,
                "label": m["label"],
                "sample_payload": sample,
                "sample_payload_json": json.dumps(sample, indent=2, sort_keys=True),
                "supported_conditions": m["supported_conditions"],
                "supported_actions": m["supported_actions"],
                "simulation_hint": _SIM_HINT,
            }
        )
    return rows
