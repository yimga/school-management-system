"""
Workflow playbook AI — onboarding / offboarding conversational guidance (batch 1394).

Grounds answers in code SOT: ``tenant_onboarding_operator_direction`` and
offboarding self-service policy (no secrets, no legal advice).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "build_onboarding_playbook_context",
    "build_offboarding_playbook_context",
]


def build_onboarding_playbook_context(
    *,
    progress: dict[str, Any] | None = None,
    blockers: list[str] | None = None,
) -> str:
    from apps.platform_runtime.tenant_onboarding_operator_direction import (
        LAUNCH_LANES,
        ONBOARDING_DIRECTION_STEPS,
    )

    lines = [
        "PLAYBOOK: Tenant onboarding (activation checklist → School Studio launch).",
        "Owners and steps (code SOT):",
    ]
    for step in ONBOARDING_DIRECTION_STEPS[:12]:
        if not isinstance(step, dict):
            continue
        lines.append(
            f"- {step.get('step_key', '')}: {step.get('name', '')} "
            f"(owner={step.get('owner', '')})"
        )
    lines.append("Launch lanes:")
    for lane in LAUNCH_LANES:
        if not isinstance(lane, dict):
            continue
        lines.append(
            f"- {lane.get('key', '')}: {lane.get('label', '')} — {lane.get('purpose', '')}"
        )
    pct = int((progress or {}).get("percent") or 0)
    lines.append(f"Current activation percent: {pct}%")
    if blockers:
        lines.append("Blockers: " + "; ".join(str(b)[:200] for b in blockers[:5]))
    na = (progress or {}).get("next_action")
    if isinstance(na, dict) and na.get("label"):
        lines.append(f"Next action: {na.get('label')}")
    lines.append(
        "Rules: recommend named checklist steps and School Studio links; "
        "never invent API keys; HITL for go-live when health is at_risk."
    )
    return "\n".join(lines)[:4000]


def build_offboarding_playbook_context(
    *,
    self_service: dict[str, Any] | None = None,
) -> str:
    ss = self_service or {}
    lines = [
        "PLAYBOOK: Tenant offboarding (export → request closure → grace → purge).",
        "Steps:",
        "1. Generate portability export (ZIP) before closure.",
        "2. Request account closure — deactivates access; schedules purge after grace.",
        "3. Cancel scheduled closure during grace if the school continues.",
        "4. Platform operator queue handles legal hold and dual approval on manager host.",
        "Retention: audit logs may be retained; tenant PII purge follows policy timer.",
        f"Self-service status: {ss.get('status', 'unknown')}",
        f"Grace days: {ss.get('grace_days', '')}",
        f"Scheduled purge: {ss.get('scheduled_purge_at', '—')}",
        "Rules: never claim immediate deletion; remind export-first; no legal advice.",
    ]
    return "\n".join(lines)[:4000]
