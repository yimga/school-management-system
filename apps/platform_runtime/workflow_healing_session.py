"""Healing session state stored on WorkflowRun.payload_summary."""

from __future__ import annotations

import uuid
from typing import Any

from django.utils import timezone

_HEALING_KEY = "healing_session"
_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})

_PHASE_PROGRESS = {
    "diagnosing": 8,
    "preflight_fix": 35,
    "requeue_queued": 75,
    "provisioning": 88,
    "verifying": 95,
    "succeeded": 100,
    "failed": 100,
    "cancelled": 100,
}


def healing_session_from_run(run: Any) -> dict[str, Any]:
    payload = getattr(run, "payload_summary", None) or {}
    if not isinstance(payload, dict):
        return {}
    session = payload.get(_HEALING_KEY)
    return dict(session) if isinstance(session, dict) else {}


def healing_session_active(run: Any) -> bool:
    session = healing_session_from_run(run)
    phase = str(session.get("phase") or "")
    return bool(session) and phase not in _TERMINAL


def start_healing_session(
    *,
    run: Any,
    chain: list[str],
    fingerprint: dict[str, Any],
    actor_user_id: str = "",
) -> dict[str, Any]:
    """Persist a new healing session on the run row."""

    from apps.platform_runtime.models import WorkflowRun

    now = timezone.now().isoformat()
    session: dict[str, Any] = {
        "session_id": str(uuid.uuid4()),
        "started_at": now,
        "started_by_user_id": str(actor_user_id or "")[:40],
        "phase": "diagnosing",
        "progress_percent": _PHASE_PROGRESS["diagnosing"],
        "current_step_label": "Analyzing failure…",
        "chain": list(chain),
        "chain_results": [],
        "error_fingerprint": fingerprint,
        "ai_diagnosis": _rule_diagnosis(fingerprint),
        "log_lines": [],
        "last_heartbeat_at": now,
    }
    payload = dict(getattr(run, "payload_summary", None) or {})
    payload[_HEALING_KEY] = session
    WorkflowRun.objects.filter(pk=run.pk).update(  # tenant-isolation-allow: healing-session-stamp-by-pk
        payload_summary=payload,
        last_heartbeat_at=timezone.now(),
    )
    run.payload_summary = payload
    return session


def update_healing_session(
    run: Any,
    *,
    phase: str | None = None,
    progress_percent: int | None = None,
    current_step_label: str | None = None,
    log_line: str | None = None,
    chain_result: dict[str, Any] | None = None,
    ai_diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from apps.platform_runtime.models import WorkflowRun

    payload = dict(getattr(run, "payload_summary", None) or {})
    session = dict(payload.get(_HEALING_KEY) or {})
    if not session:
        return {}

    if phase:
        session["phase"] = phase
        if progress_percent is None and phase in _PHASE_PROGRESS:
            session["progress_percent"] = _PHASE_PROGRESS[phase]
    if progress_percent is not None:
        session["progress_percent"] = max(0, min(100, int(progress_percent)))
    if current_step_label:
        session["current_step_label"] = current_step_label[:240]
    if log_line:
        lines = list(session.get("log_lines") or [])
        lines.append(log_line[:500])
        session["log_lines"] = lines[-8:]
    if chain_result:
        results = list(session.get("chain_results") or [])
        results.append(chain_result)
        session["chain_results"] = results[-12:]
    if ai_diagnosis:
        session["ai_diagnosis"] = ai_diagnosis

    session["last_heartbeat_at"] = timezone.now().isoformat()
    payload[_HEALING_KEY] = session
    WorkflowRun.objects.filter(pk=run.pk).update(  # tenant-isolation-allow: healing-session-update-by-pk
        payload_summary=payload,
        last_heartbeat_at=timezone.now(),
    )
    run.payload_summary = payload
    return session


def _rule_diagnosis(fingerprint: dict[str, Any]) -> dict[str, Any]:
    plan = []
    for step in fingerprint.get("recommended_chain") or []:
        plan.append(str(step).replace("_", " "))
    return {
        "title": fingerprint.get("human_title") or "Diagnosis",
        "cause": fingerprint.get("human_cause") or "",
        "plan": plan or ["Re-queue provisioning"],
        "confidence": fingerprint.get("confidence") or "medium",
        "source": fingerprint.get("diagnosis_source") or "rule_based",
    }
