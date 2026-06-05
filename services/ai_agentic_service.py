"""Agentic AI — Phase 1 (read-only) orchestration.

This is the governed layer that makes ``services.ai_agentic`` (the kernel) and
``services.ai_agentic_runners`` (the read-only runner bridge) actually usable,
within the platform's AI Operating Layer posture (drafts/insights only, human in
the loop, audit-traced). It closes gaps **G3** (a real entry point + the
propose→execute split with server-side confirmation) and **G4** (a durable,
append-only audit row per attempt) from ``docs/AI_AGENTIC_ACTIONS_DESIGN.md``.

Phase-1 invariants enforced HERE (belt-and-suspenders over the kernel):
1. **Flag-gated, default off.** Nothing runs unless ``RMC_AI_AGENTIC_ENABLED`` is
   set AND the platform AI gate (``RUNMYCAMPUS_AI_ENABLED`` + tenant policy) is on.
2. **Read-only ONLY.** ``propose`` drops any non-``read_only`` action and any
   action without a bridged read-only runner. ``execute`` hard-refuses to run an
   action whose spec impact is not ``read_only`` — even if it is registered.
3. **Server-side confirmation.** ``ctx.confirmed_by`` is set from the
   authenticated user id passed by the view, NEVER from a client payload.
4. **Every attempt is audited** — ok, blocked, or error — to
   ``AIAgenticActionAudit`` (actor + params hashed, no PII).

Boundary: imports the kernel + ``services.ai_helpers`` only — NEVER
``services.ai_gateway`` (the boundary scanner enforces this).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from typing import Any, Callable

from services.ai_agentic import (
    ActionContext,
    ActionSpec,
    ExecutionResult,
    ProposedAction,
    execute_action,
    get_action,
    list_actions,
    propose_actions,
)
from services.ai_agentic_runners import get_runner_for, list_bridged_actions

logger = logging.getLogger(__name__)

_READ_ONLY = "read_only"


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def _agentic_flag_on() -> bool:
    return os.environ.get("RMC_AI_AGENTIC_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def agentic_phase1_enabled(*, school=None) -> bool:
    """True only when the dedicated agentic flag AND the platform AI gate are on.

    The platform gate is reused from ``ai_governance`` so tenant ``ai_policy``
    (``tenant_ai_enabled``) can still veto, consistent with every other AI surface.
    """
    if not _agentic_flag_on():
        return False
    try:
        from apps.platform_runtime.ai_governance import resolve_effective_enabled

        return bool(resolve_effective_enabled(school=school))
    except Exception:  # noqa: BLE001 — never let a gate-resolution error enable AI
        logger.debug("agentic_phase1_enabled: governance gate unresolved", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Read-only action surface
# ---------------------------------------------------------------------------

def available_readonly_actions() -> tuple[ActionSpec, ...]:
    """Registered ``read_only`` actions that also have a bridged runner.

    This is the *entire* Phase-1 action surface — nothing else can execute.
    """
    bridged = set(list_bridged_actions())
    return tuple(
        spec
        for spec in list_actions()
        if spec.impact == _READ_ONLY and spec.name in bridged
    )


def _is_phase1_eligible(spec: ActionSpec | None) -> bool:
    if spec is None:
        return False
    if spec.impact != _READ_ONLY:
        return False
    return get_runner_for(spec.name) is not None


# ---------------------------------------------------------------------------
# Propose
# ---------------------------------------------------------------------------

def _make_live_propose(school) -> Callable[..., Any]:
    """Adapter mapping the kernel's propose callable to ``ai_helpers.invoke_json_task``."""

    def _adapter(*, task_id: str, prompt: str, schema_hint: dict, tenant_id: str) -> dict:
        from services import ai_helpers

        full_prompt = (
            f"{prompt}\n\nRespond ONLY with a JSON object of this shape:\n"
            f"{json.dumps(schema_hint)}"
        )
        try:
            out = ai_helpers.invoke_json_task(
                school=school,
                task_type_name="NARRATIVE",
                prompt=full_prompt,
                prompt_type="agentic_propose",
                content_sensitivity="standard",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("agentic live-propose adapter failed: %s", exc)
            return {}
        if not out:
            return {}
        obj, _meta = out
        return obj if isinstance(obj, dict) else {}

    return _adapter


def propose(
    *,
    prompt: str,
    ctx: ActionContext,
    school=None,
    extra_params: dict | None = None,
) -> tuple[ProposedAction, ...]:
    """Generate Phase-1 proposals, filtered to read-only + bridged actions.

    Uses the live gateway (via ``ai_helpers``) when AI is available, else the
    kernel's deterministic mock router. Either way, the result is filtered so
    only safe, executable read-only actions survive.
    """
    if not prompt or not prompt.strip():
        return ()

    live = False
    helper = None
    try:
        from services import ai_helpers

        live = bool(ai_helpers.is_ai_available())
    except Exception:  # noqa: BLE001
        live = False
    if live:
        helper = _make_live_propose(school)

    raw = propose_actions(
        prompt=prompt,
        ctx=ctx,
        mock_mode=not live,
        helper_invoke_json_task=helper,
    )

    out: list[ProposedAction] = []
    for p in raw:
        if not _is_phase1_eligible(get_action(p.action)):
            continue
        params = dict(p.params or {})
        if extra_params:
            # Caller-supplied params (e.g. class_id) win — they are explicit operator input.
            params.update({k: v for k, v in extra_params.items() if v not in (None, "")})
        out.append(
            ProposedAction(
                action=p.action,
                params=params,
                rationale=p.rationale,
                confidence=p.confidence,
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# Execute (read-only) + durable audit
# ---------------------------------------------------------------------------

def _hash12(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:12]


def _params_hash(params: dict | None) -> str:
    try:
        canonical = json.dumps(params or {}, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        canonical = str(params)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _write_audit(
    *,
    audit_id: str,
    ctx: ActionContext,
    proposed: ProposedAction,
    spec: ActionSpec | None,
    result: ExecutionResult,
) -> None:
    """Durable, fail-soft append-only audit write. Never breaks the request."""
    try:
        from apps.platform_runtime.models_agentic_audit import (
            AIAgenticActionAudit,
            AIAgenticActionOutcome,
        )

        if result.ok:
            outcome = AIAgenticActionOutcome.OK
        elif result.blocked_reason:
            outcome = AIAgenticActionOutcome.BLOCKED
        else:
            outcome = AIAgenticActionOutcome.ERROR

        AIAgenticActionAudit.objects.create(
            audit_id=audit_id,
            tenant_id=(ctx.tenant_id or "")[:128],
            actor_user_id_hash=_hash12(ctx.user_id),
            confirmed_by_hash=_hash12(ctx.confirmed_by) if ctx.confirmed_by else "",
            action=(proposed.action or "")[:128],
            impact=(spec.impact if spec else "")[:16],
            params_hash=_params_hash(proposed.params),
            executed=bool(result.ok and result.result not in (None, {"ready_to_run": True})),
            outcome=outcome,
            blocked_reason=(result.blocked_reason or "")[:64],
        )
    except Exception:  # noqa: BLE001 — audit must never break the action path
        logger.exception("agentic durable audit write failed action=%s", proposed.action)


def execute(
    *,
    proposed: ProposedAction,
    ctx: ActionContext,
    confirmed_by_user_id: str,
    school=None,
) -> ExecutionResult:
    """Execute a single read-only action, server-side confirmed and audited.

    ``confirmed_by_user_id`` MUST come from the authenticated session, never from
    a client payload. Refuses anything whose spec impact is not ``read_only``.
    """
    spec = get_action(proposed.action)

    # Hard read-only refusal — defense beyond the runner-map filter.
    if spec is None or spec.impact != _READ_ONLY:
        result = ExecutionResult(
            ok=False,
            action=proposed.action,
            error="Phase 1 permits read-only actions only.",
            blocked_reason="not_read_only",
        )
        audit_id = "ag_" + uuid.uuid4().hex[:16]
        confirmed_ctx = _with_confirmation(ctx, confirmed_by_user_id)
        _write_audit(audit_id=audit_id, ctx=confirmed_ctx, proposed=proposed, spec=spec, result=result)
        return result

    runner = get_runner_for(proposed.action)
    if runner is None:
        result = ExecutionResult(
            ok=False,
            action=proposed.action,
            error="No read-only runner bound for this action.",
            blocked_reason="no_runner",
        )
        audit_id = "ag_" + uuid.uuid4().hex[:16]
        confirmed_ctx = _with_confirmation(ctx, confirmed_by_user_id)
        _write_audit(audit_id=audit_id, ctx=confirmed_ctx, proposed=proposed, spec=spec, result=result)
        return result

    confirmed_ctx = _with_confirmation(ctx, confirmed_by_user_id)
    result = execute_action(proposed, ctx=confirmed_ctx, runner=runner)
    audit_id = result.audit_id or ("ag_" + uuid.uuid4().hex[:16])
    _write_audit(audit_id=audit_id, ctx=confirmed_ctx, proposed=proposed, spec=spec, result=result)
    return result


def _with_confirmation(ctx: ActionContext, confirmed_by_user_id: str) -> ActionContext:
    """Return a copy of ``ctx`` with ``confirmed_by`` set from the server side."""
    return ActionContext(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        user_roles=ctx.user_roles,
        confirmed_by=str(confirmed_by_user_id or ""),
    )


# ---------------------------------------------------------------------------
# Operator surface helpers
# ---------------------------------------------------------------------------

def recent_audit(*, limit: int = 25, tenant_id: str | None = None) -> list[dict]:
    """Most-recent-first audit tail for the operator surface (PII-free rows)."""
    try:
        from apps.platform_runtime.models_agentic_audit import AIAgenticActionAudit

        qs = AIAgenticActionAudit.objects.all()
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        rows = []
        for r in qs.order_by("-created_at")[: max(1, min(limit, 200))]:
            rows.append(
                {
                    "audit_id": r.audit_id,
                    "action": r.action,
                    "impact": r.impact,
                    "outcome": r.outcome,
                    "executed": r.executed,
                    "blocked_reason": r.blocked_reason,
                    "actor": r.actor_user_id_hash,
                    "created_at": r.created_at,
                }
            )
        return rows
    except Exception:  # noqa: BLE001
        logger.debug("agentic recent_audit unavailable", exc_info=True)
        return []
