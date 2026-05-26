"""Wave K (v3.95.0 — 2026-05-26) — Agentic AI action plumbing.

Counters the Canvas IgniteAgent / Gemini-in-Classroom competitive gap with
**permission-aware, audit-traced action execution**. Three principles:

1. NEVER auto-execute mutating actions. The agent *proposes* actions; a human
   *confirms*; the runner *executes*.
2. Every action declares its required role + tenant scope + reversibility.
   The verifier blocks anything outside the caller's grant before the runner
   ever runs.
3. The kernel routes AI calls through ``services.ai_helpers`` only — NEVER
   through ``services.ai_gateway`` (the boundary scanner enforces this).
   Mock-mode short-circuits the helper so tests run without LiteLLM.

This module is intentionally minimal — it's the kernel, not the UI. Wizard /
copilot / portal surfaces wire to ``propose_actions`` + ``execute_action``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

_READ_ONLY = "read_only"
_MUTATING = "mutating"
_DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ActionSpec:
    """A single agent-callable action, declarative."""

    name: str
    description: str
    impact: str  # _READ_ONLY / _MUTATING / _DESTRUCTIVE
    required_roles: tuple[str, ...] = ()
    reversible: bool = True
    requires_confirmation: bool = True
    parameters: tuple[str, ...] = ()


_REGISTRY: dict[str, ActionSpec] = {}


def register_action(spec: ActionSpec) -> None:
    """Register an action spec. Subsequent registrations overwrite (last wins).
    Idempotent at import time so apps can re-register at startup."""
    _REGISTRY[spec.name] = spec


def get_action(name: str) -> ActionSpec | None:
    return _REGISTRY.get(name)


def list_actions() -> tuple[ActionSpec, ...]:
    return tuple(_REGISTRY.values())


def clear_registry_for_tests() -> None:
    """Test helper — wipe the registry. Production code MUST NOT call this."""
    _REGISTRY.clear()


# Default seeded actions — covers the 8 highest-frequency agent use cases.
def _seed_default_actions() -> None:
    for spec in (
        ActionSpec(
            name="summarize_attendance_report",
            description="Read-only summary of attendance for a class / cohort.",
            impact=_READ_ONLY,
            required_roles=("TEACHER", "DEAN", "PRINCIPAL", "LEADERSHIP", "ADMIN"),
            reversible=True,
            requires_confirmation=False,
            parameters=("class_id", "date_range"),
        ),
        ActionSpec(
            name="summarize_outstanding_fees",
            description="Read-only summary of outstanding fees by class.",
            impact=_READ_ONLY,
            required_roles=("BURSAR", "FINANCE_STAFF", "PRINCIPAL", "LEADERSHIP", "ADMIN"),
            reversible=True,
            requires_confirmation=False,
            parameters=("class_id",),
        ),
        ActionSpec(
            name="draft_parent_announcement",
            description="Drafts a parent-facing announcement text. Never sends.",
            impact=_READ_ONLY,
            required_roles=("TEACHER", "COMMS_STAFF", "PRINCIPAL", "LEADERSHIP", "ADMIN"),
            reversible=True,
            requires_confirmation=False,
            parameters=("topic", "audience", "locale"),
        ),
        ActionSpec(
            name="send_parent_message",
            description="Sends a WhatsApp / SMS / email to a parent. MUTATING.",
            impact=_MUTATING,
            required_roles=("COMMS_STAFF", "PRINCIPAL", "LEADERSHIP", "ADMIN"),
            reversible=False,
            requires_confirmation=True,
            parameters=("parent_id", "channel", "body"),
        ),
        ActionSpec(
            name="mark_student_absent",
            description="Marks a student absent for today. MUTATING.",
            impact=_MUTATING,
            required_roles=("TEACHER", "PRINCIPAL", "LEADERSHIP", "ADMIN"),
            reversible=True,
            requires_confirmation=True,
            parameters=("student_id", "date", "reason"),
        ),
        ActionSpec(
            name="apply_fee_waiver",
            description="Applies a fee waiver to a student account. MUTATING.",
            impact=_MUTATING,
            required_roles=("BURSAR", "PRINCIPAL", "LEADERSHIP", "ADMIN"),
            reversible=True,
            requires_confirmation=True,
            parameters=("student_id", "amount_minor", "reason"),
        ),
        ActionSpec(
            name="schedule_parent_callback",
            description="Schedules a callback in the office queue.",
            impact=_MUTATING,
            required_roles=("COMMS_STAFF", "ADMIN"),
            reversible=True,
            requires_confirmation=True,
            parameters=("parent_id", "preferred_time"),
        ),
        ActionSpec(
            name="purge_student_record",
            description="Permanently deletes a student record. DESTRUCTIVE.",
            impact=_DESTRUCTIVE,
            required_roles=("PRINCIPAL", "LEADERSHIP", "DPO", "ADMIN"),
            reversible=False,
            requires_confirmation=True,
            parameters=("student_id", "justification"),
        ),
    ):
        register_action(spec)


_seed_default_actions()


# ---------------------------------------------------------------------------
# Proposal + execution dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProposedAction:
    """An action the agent suggests in response to a user prompt."""

    action: str
    params: dict[str, Any]
    rationale: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class ActionContext:
    """Caller's grant — passed to the verifier and runner."""

    tenant_id: str
    user_id: str
    user_roles: tuple[str, ...]
    confirmed_by: str = ""  # populated at execute_action; empty during propose


@dataclass
class ExecutionResult:
    ok: bool
    action: str
    result: Any = None
    error: str = ""
    audit_id: str = ""
    blocked_reason: str = ""


# ---------------------------------------------------------------------------
# Permission verifier
# ---------------------------------------------------------------------------

def verify_permission(action_spec: ActionSpec, ctx: ActionContext) -> str:
    """Return empty string if permitted; reason string if blocked."""
    if not ctx.tenant_id:
        return "tenant_id missing on context"
    if not ctx.user_id:
        return "user_id missing on context"
    if action_spec.required_roles:
        if not (set(ctx.user_roles) & set(action_spec.required_roles)):
            return (
                f"user lacks required role for {action_spec.name} "
                f"(needs one of: {','.join(action_spec.required_roles)})"
            )
    return ""


# ---------------------------------------------------------------------------
# Proposal pipeline
# ---------------------------------------------------------------------------

def propose_actions(
    *,
    prompt: str,
    ctx: ActionContext,
    mock_mode: bool = True,
    helper_invoke_json_task: Callable[..., Any] | None = None,
) -> tuple[ProposedAction, ...]:
    """Generate a list of proposed actions for a user prompt.

    ``mock_mode=True`` (default in tests + on platforms without LITELLM env)
    returns deterministic proposals from a small keyword router. Live mode
    routes through ``services.ai_helpers.invoke_json_task``.
    """
    prompt_n = (prompt or "").strip().lower()
    if not prompt_n:
        return ()

    if mock_mode or helper_invoke_json_task is None:
        return _mock_propose(prompt_n)

    schema_hint = {
        "actions": [{"action": "...", "params": {}, "rationale": "...", "confidence": 0.0}]
    }
    try:
        raw = helper_invoke_json_task(
            task_id="ai_agentic.propose_actions",
            prompt=prompt,
            schema_hint=schema_hint,
            tenant_id=ctx.tenant_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ai_agentic propose_actions helper failed: %s", exc)
        return ()

    return _parse_helper_response(raw)


_MOCK_KEYWORD_MAP: tuple[tuple[tuple[str, ...], str, dict[str, Any], str], ...] = (
    (("attendance", "absent today", "who is in class"),
     "summarize_attendance_report",
     {"date_range": "today"}, "Mock: keyword 'attendance' triggered summary."),
    (("fees", "outstanding", "owed"),
     "summarize_outstanding_fees",
     {}, "Mock: keyword 'fees' triggered summary."),
    (("draft", "announce", "message to parents", "newsletter"),
     "draft_parent_announcement",
     {"audience": "all_parents", "locale": "en"},
     "Mock: keyword 'draft/announcement' triggered draft."),
    (("send to parent", "notify parent"),
     "send_parent_message",
     {"channel": "whatsapp"}, "Mock: keyword 'notify' triggered send."),
    (("mark absent", "absent for"),
     "mark_student_absent",
     {"reason": "unspecified"}, "Mock: keyword 'mark absent' triggered."),
    (("waive fee", "waiver"),
     "apply_fee_waiver",
     {}, "Mock: keyword 'waiver' triggered."),
    (("callback", "call back"),
     "schedule_parent_callback",
     {}, "Mock: keyword 'callback' triggered."),
)


def _mock_propose(prompt_n: str) -> tuple[ProposedAction, ...]:
    out: list[ProposedAction] = []
    for kws, action, params, rationale in _MOCK_KEYWORD_MAP:
        if any(kw in prompt_n for kw in kws):
            out.append(ProposedAction(
                action=action, params=params, rationale=rationale, confidence=0.7,
            ))
    return tuple(out)


def _parse_helper_response(raw: Any) -> tuple[ProposedAction, ...]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return ()
    if not isinstance(raw, dict):
        return ()
    actions_raw = raw.get("actions")
    if not isinstance(actions_raw, list):
        return ()
    out: list[ProposedAction] = []
    for a in actions_raw:
        if not isinstance(a, dict):
            continue
        name = (a.get("action") or "").strip()
        if not name or name not in _REGISTRY:
            continue
        params = a.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        try:
            confidence = float(a.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        out.append(ProposedAction(
            action=name,
            params=params,
            rationale=str(a.get("rationale") or ""),
            confidence=confidence,
        ))
    return tuple(out)


# ---------------------------------------------------------------------------
# Execution pipeline
# ---------------------------------------------------------------------------

def execute_action(
    proposed: ProposedAction,
    *,
    ctx: ActionContext,
    runner: Callable[[ProposedAction, ActionContext], Any] | None = None,
    audit_sink: Callable[[dict], None] | None = None,
) -> ExecutionResult:
    """Execute a confirmed action.

    Refuses to run when (a) the action isn't registered, (b) the context
    fails ``verify_permission``, or (c) ``requires_confirmation`` is True
    and ``ctx.confirmed_by`` is empty.
    """
    spec = get_action(proposed.action)
    if spec is None:
        return ExecutionResult(
            ok=False, action=proposed.action,
            error=f"unknown action {proposed.action!r}",
            blocked_reason="unknown_action",
        )

    perm_err = verify_permission(spec, ctx)
    if perm_err:
        return ExecutionResult(
            ok=False, action=proposed.action,
            error=perm_err,
            blocked_reason="permission_denied",
        )

    if spec.requires_confirmation and not ctx.confirmed_by:
        return ExecutionResult(
            ok=False, action=proposed.action,
            error="action requires confirmation but ctx.confirmed_by is empty",
            blocked_reason="confirmation_required",
        )

    if runner is None:
        # No runner provided — return ready-to-run shape.
        audit_id = _audit_id(proposed, ctx)
        if audit_sink:
            audit_sink({
                "action": proposed.action,
                "tenant_id": ctx.tenant_id,
                "user_id_hash": hashlib.sha256(ctx.user_id.encode()).hexdigest()[:12],
                "audit_id": audit_id,
                "executed": False,
            })
        return ExecutionResult(ok=True, action=proposed.action,
                               audit_id=audit_id, result={"ready_to_run": True})

    try:
        result = runner(proposed, ctx)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ai_agentic runner failed action=%s err=%s",
                         proposed.action, exc)
        return ExecutionResult(
            ok=False, action=proposed.action, error=str(exc),
            blocked_reason="runner_exception",
        )

    audit_id = _audit_id(proposed, ctx)
    if audit_sink:
        try:
            audit_sink({
                "action": proposed.action,
                "tenant_id": ctx.tenant_id,
                "user_id_hash": hashlib.sha256(ctx.user_id.encode()).hexdigest()[:12],
                "audit_id": audit_id,
                "executed": True,
                "impact": spec.impact,
            })
        except Exception:  # noqa: BLE001
            logger.exception("ai_agentic audit sink failed")
    return ExecutionResult(ok=True, action=proposed.action,
                           result=result, audit_id=audit_id)


def _audit_id(proposed: ProposedAction, ctx: ActionContext) -> str:
    seed = f"{ctx.tenant_id}|{ctx.user_id}|{proposed.action}|{time.time_ns()}"
    return "ag_" + hashlib.sha256(seed.encode()).hexdigest()[:16]
