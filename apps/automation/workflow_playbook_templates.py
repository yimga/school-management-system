"""
Ready-made playbook definitions for Studio guidance (batch 1147+).

Each entry ties a trigger to suggested condition/action narration and a deterministic
simulation sample. Does not auto-create tenant workflows — operators instantiate from
the visual designer or APIs.
"""

from __future__ import annotations

import json
from typing import Any

from apps.automation.workflow_trigger_catalog import sample_payload_for_trigger


def _pb(
    *,
    slug: str,
    title: str,
    trigger_key: str,
    condition_summary: str,
    action_summary: str,
    owner_audience: str,
    risk_level: str,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "title": title,
        "trigger_key": trigger_key,
        "condition_summary": condition_summary,
        "action_summary": action_summary,
        "owner_audience": owner_audience,
        "risk_level": risk_level,
    }


READY_PLAYBOOKS: tuple[dict[str, Any], ...] = (
    _pb(
        slug="missing_attendance_reminder",
        title="Missing attendance reminder",
        trigger_key="attendance_saved",
        condition_summary="saved_count == 0 or absence_flag is true for roster slice",
        action_summary="notify attendance clerk channel=log; emit_event attendance.followup",
        owner_audience="School admin; attendance office",
        risk_level="low",
    ),
    _pb(
        slug="payment_overdue_escalation",
        title="Payment overdue escalation",
        trigger_key="payment_failed",
        condition_summary="retry_count >= 2 OR failure_reason in {card_declined, insufficient_funds}",
        action_summary="notify finance lead; emit_event billing.escalation",
        owner_audience="Finance; registrar",
        risk_level="medium",
    ),
    _pb(
        slug="marks_missing_follow_up",
        title="Marks missing follow-up",
        trigger_key="marks_submitted",
        condition_summary="payload marks_complete == false OR pending_review flag",
        action_summary="notify head of academics; create_record remediation_stub",
        owner_audience="Academic lead; department heads",
        risk_level="medium",
    ),
    _pb(
        slug="report_published_notification",
        title="Report published notification",
        trigger_key="report_generated",
        condition_summary="report_type in {term_summary, annual}",
        action_summary="notify guardians preview channel=log; emit_event reports.published",
        owner_audience="Reports office; communications",
        risk_level="low",
    ),
    _pb(
        slug="student_risk_intervention",
        title="Student risk intervention",
        trigger_key="student_risk_detected",
        condition_summary="risk_tier == high OR risk_score >= 0.75",
        action_summary="notify counselling coordinator; emit_event student.risk.pipeline",
        owner_audience="Counselling; safeguarding lead",
        risk_level="high",
    ),
    _pb(
        slug="offline_conflict_follow_up",
        title="Offline conflict follow-up",
        trigger_key="offline_action_conflict",
        condition_summary="conflict_entity_type matches protected domains (grades, attendance)",
        action_summary="notify IT/integration owner; emit_event sync.conflict.open",
        owner_audience="IT admin; data steward",
        risk_level="medium",
    ),
)


def playbook_simulation_sample(school_id: str, playbook: dict[str, Any]) -> dict[str, Any]:
    """Merge catalog sample for the playbook trigger."""
    return sample_payload_for_trigger(school_id, str(playbook["trigger_key"]))


def enrich_playbooks_for_template(school_id: str) -> list[dict[str, Any]]:
    """Attach simulation_sample_json for Studio rendering."""
    out: list[dict[str, Any]] = []
    for pb in READY_PLAYBOOKS:
        sample = playbook_simulation_sample(school_id, pb)
        row = dict(pb)
        row["simulation_sample"] = sample
        row["simulation_sample_json"] = json.dumps(sample, indent=2, sort_keys=True)
        out.append(row)
    return out
