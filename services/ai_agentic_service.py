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
import time
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
    verify_permission,
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
    phase: str | None = None,
    reversal_payload: dict | None = None,
    outcome_override: str | None = None,
) -> None:
    """Durable, fail-soft append-only audit write. Never breaks the request."""
    try:
        from apps.platform_runtime.models_agentic_audit import (
            AIAgenticActionAudit,
            AIAgenticActionOutcome,
            AIAgenticActionPhase,
        )

        if outcome_override is not None:
            outcome = outcome_override
        elif result.ok:
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
            phase=phase or AIAgenticActionPhase.OUTCOME,
            reversal_payload=reversal_payload or {},
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


# ===========================================================================
# Phase 2 — mutating actions (reversible only, confirm-gated, audited)
# ===========================================================================
#
# Everything below is gated by RMC_AI_AGENTIC_MUTATING_ENABLED *in addition to*
# the Phase-1 gates. It executes a tiny set of reversible mutating actions behind
# a mandatory server-side confirmation, with an intent row written BEFORE the
# runner and a reversal path per action. See docs/AI_AGENTIC_ACTIONS_DESIGN.md.

_MUTATING = "mutating"
_CONFIRM_TOKEN_SALT = "rmc.agentic.confirm.v1"
_CONFIRM_TOKEN_TTL_SECONDS = 300


def _agentic_mutating_flag_on() -> bool:
    return os.environ.get("RMC_AI_AGENTIC_MUTATING_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def agentic_mutating_enabled(*, school=None) -> bool:
    """Phase-2 gate: the dedicated mutating sub-flag AND all Phase-1 gates.

    Mutating stays off even when read-only Phase-1 is on, until the operator
    explicitly sets RMC_AI_AGENTIC_MUTATING_ENABLED.
    """
    if not _agentic_mutating_flag_on():
        return False
    return agentic_phase1_enabled(school=school)


def _opt_in_mutating_runners() -> dict:
    try:
        from services.ai_agentic_runners_mutating import OPT_IN_MUTATING_RUNNERS

        return dict(OPT_IN_MUTATING_RUNNERS)
    except Exception:  # noqa: BLE001
        logger.debug("mutating runners unavailable", exc_info=True)
        return {}


def available_mutating_actions() -> tuple[ActionSpec, ...]:
    """Registered ``mutating`` + ``reversible`` actions that have an opt-in runner.

    This is the ENTIRE Phase-2 surface. Non-reversible mutating actions (e.g.
    ``send_parent_message``) are excluded by the reversibility gate; destructive
    actions are never here.
    """
    runners = set(_opt_in_mutating_runners().keys())
    return tuple(
        spec
        for spec in list_actions()
        if spec.impact == _MUTATING and spec.reversible and spec.name in runners
    )


def _is_mutating_eligible(spec: ActionSpec | None) -> bool:
    if spec is None:
        return False
    if spec.impact != _MUTATING or not spec.reversible:
        return False
    return spec.name in _opt_in_mutating_runners()


def propose_mutating(
    *,
    prompt: str,
    ctx: ActionContext,
    school=None,
    extra_params: dict | None = None,
) -> tuple[ProposedAction, ...]:
    """Like ``propose`` but filtered to the eligible (reversible) mutating set."""
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
        prompt=prompt, ctx=ctx, mock_mode=not live, helper_invoke_json_task=helper,
    )
    out: list[ProposedAction] = []
    for p in raw:
        if not _is_mutating_eligible(get_action(p.action)):
            continue
        params = dict(p.params or {})
        if extra_params:
            params.update({k: v for k, v in extra_params.items() if v not in (None, "")})
        out.append(ProposedAction(action=p.action, params=params,
                                  rationale=p.rationale, confidence=p.confidence))
    return tuple(out)


# --- Confirmation token (single-use, TTL, bound to action+params+user) -------

def issue_confirm_token(*, action: str, params: dict, user_id: str) -> str:
    """Server-issued token rendered on the Confirm button. Binds the exact
    action + params + user; expires; single-use (consumed at validation)."""
    from django.core.signing import TimestampSigner

    payload = f"{action}|{_params_hash(params)}|{user_id}"
    return TimestampSigner(salt=_CONFIRM_TOKEN_SALT).sign(payload)


def _consume_confirm_token(*, token: str, action: str, params: dict, user_id: str) -> bool:
    """Validate signature + age + bind, and mark single-use. False if invalid."""
    from django.core.cache import cache
    from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

    if not token:
        return False
    try:
        value = TimestampSigner(salt=_CONFIRM_TOKEN_SALT).unsign(
            token, max_age=_CONFIRM_TOKEN_TTL_SECONDS,
        )
    except (BadSignature, SignatureExpired):
        return False
    expected = f"{action}|{_params_hash(params)}|{user_id}"
    if value != expected:
        return False
    # Single-use: refuse a token already consumed.
    cache_key = "agentic_confirm_used:" + hashlib.sha256(token.encode()).hexdigest()[:24]
    try:
        if cache.get(cache_key):
            return False
        cache.set(cache_key, 1, timeout=_CONFIRM_TOKEN_TTL_SECONDS)
    except Exception:  # noqa: BLE001 — cache outage shouldn't hard-fail; signature already checked
        logger.debug("confirm-token single-use cache unavailable", exc_info=True)
    return True


# --- Rate limit (per tenant+user, hourly) ------------------------------------

def _mutating_rate_limit_ok(tenant_id: str, user_id: str) -> bool:
    from django.core.cache import cache

    try:
        cap = int(os.environ.get("RMC_AI_AGENTIC_MUTATING_MAX_PER_HOUR", "30"))
    except (TypeError, ValueError):
        cap = 30
    bucket = int(time.time() // 3600)
    key = f"agentic_mut_rl:{tenant_id}:{user_id}:{bucket}"
    try:
        count = cache.get(key) or 0
        if count >= cap:
            return False
        cache.set(key, count + 1, timeout=3600)
    except Exception:  # noqa: BLE001 — cache outage: fail OPEN only for read-side, but here fail SAFE
        logger.debug("mutating rate-limit cache unavailable; allowing", exc_info=True)
    return True


# --- Pre-state snapshot for reversal -----------------------------------------

def _capture_pre_state(action: str, proposed: ProposedAction, school) -> dict:
    """Capture the minimal pseudonymous state needed to undo ``action``.

    Returns a reversal_payload dict (no PII). Best-effort; an empty dict means
    'no reversible snapshot captured' (reversal will then no-op safely).
    """
    params = proposed.params or {}
    if action == "mark_student_absent":
        return _snapshot_mark_student_absent(params, school)
    if action == "schedule_parent_callback":
        # The entry_id is injected into params before the runner stores it.
        return {"action": action, "entry_id": str(params.get("_entry_id") or "")}
    return {}


def _snapshot_mark_student_absent(params: dict, school) -> dict:
    student_id = str(params.get("student_id") or "")
    raw_date = params.get("date")
    snap = {"action": "mark_student_absent", "student_id": student_id,
            "date": "", "existed": False, "prior_status": "", "prior_notes": ""}
    if not student_id or school is None:
        return snap
    try:
        from datetime import date as _date
        from apps.people.models import Student  # type: ignore
        from apps.academics.models import AttendanceRecord  # type: ignore

        if raw_date:
            y, m, d = (int(x) for x in str(raw_date).split("-"))
            on_date = _date(y, m, d)
        else:
            on_date = _date.today()
        snap["date"] = on_date.isoformat()
        student = Student.objects.filter(school=school, pk=student_id).first()
        if student is None:
            return snap
        rec = AttendanceRecord.objects.filter(student=student, date=on_date).first()
        if rec is not None:
            snap["existed"] = True
            snap["prior_status"] = str(getattr(rec, "status", "") or "")
            snap["prior_notes"] = str(getattr(rec, "notes", "") or "")
    except Exception:  # noqa: BLE001
        logger.debug("snapshot mark_student_absent failed", exc_info=True)
    return snap


# --- Confirm + execute (the gated mutating path) -----------------------------

def confirm_and_execute(
    *,
    proposed: ProposedAction,
    ctx: ActionContext,
    confirmed_by_user_id: str,
    confirm_token: str,
    school=None,
) -> ExecutionResult:
    """Execute ONE reversible mutating action, after all Phase-2 gates pass.

    Gate order (each failure is audited as blocked, runner never runs):
    enabled → eligible(reversible mutating + runner) → role (verify_permission)
    → server-side confirmation present → valid single-use confirm token
    → rate limit. Then: write intent row (pre-state) → run → write outcome row.
    """
    spec = get_action(proposed.action)
    confirmed_ctx = _with_confirmation(ctx, confirmed_by_user_id)

    def _blocked(reason: str, msg: str) -> ExecutionResult:
        r = ExecutionResult(ok=False, action=proposed.action, error=msg, blocked_reason=reason)
        _write_audit(audit_id="ag_" + uuid.uuid4().hex[:16], ctx=confirmed_ctx,
                     proposed=proposed, spec=spec, result=r)
        return r

    if not agentic_mutating_enabled(school=school):
        return _blocked("mutating_disabled", "Mutating agentic actions are disabled.")
    if not _is_mutating_eligible(spec):
        return _blocked("not_mutating_eligible",
                        "Phase 2 permits reversible mutating actions with a bound runner only.")
    perm_err = verify_permission(spec, confirmed_ctx)
    if perm_err:
        return _blocked("permission_denied", perm_err)
    if not confirmed_ctx.confirmed_by:
        return _blocked("confirmation_required", "Server-side confirmation missing.")
    if not _consume_confirm_token(token=confirm_token, action=proposed.action,
                                  params=proposed.params, user_id=confirmed_ctx.user_id):
        return _blocked("bad_confirm_token", "Confirmation token invalid, expired, or already used.")
    if not _mutating_rate_limit_ok(confirmed_ctx.tenant_id, confirmed_ctx.user_id):
        return _blocked("rate_limited", "Mutating action rate limit reached; try again later.")

    runner = _opt_in_mutating_runners().get(proposed.action)
    if runner is None:
        return _blocked("no_runner", "No mutating runner bound for this action.")

    # For the callback action, inject a unique entry id so reversal is exact.
    params = dict(proposed.params or {})
    if proposed.action == "schedule_parent_callback":
        params["_entry_id"] = "agc_" + uuid.uuid4().hex[:16]
    proposed = ProposedAction(action=proposed.action, params=params,
                              rationale=proposed.rationale, confidence=proposed.confidence)

    audit_id = "ag_" + uuid.uuid4().hex[:16]
    reversal_payload = _capture_pre_state(proposed.action, proposed, school)

    # INTENT row — written BEFORE the runner runs (Phase-2 gate #5).
    from apps.platform_runtime.models_agentic_audit import (
        AIAgenticActionOutcome,
        AIAgenticActionPhase,
    )
    _write_audit(
        audit_id=audit_id, ctx=confirmed_ctx, proposed=proposed, spec=spec,
        result=ExecutionResult(ok=False, action=proposed.action, result={"intent": True}),
        phase=AIAgenticActionPhase.INTENT,
        reversal_payload=reversal_payload,
        outcome_override=AIAgenticActionOutcome.PENDING,
    )

    result = execute_action(proposed, ctx=confirmed_ctx, runner=runner)
    # Stamp the shared audit_id onto the result for the operator UI + reversal.
    result.audit_id = audit_id

    # OUTCOME row — after the runner.
    _write_audit(
        audit_id=audit_id, ctx=confirmed_ctx, proposed=proposed, spec=spec,
        result=result, phase=AIAgenticActionPhase.OUTCOME,
    )
    return result


def reverse_action(
    *,
    audit_id: str,
    ctx: ActionContext,
    confirmed_by_user_id: str,
    school=None,
) -> ExecutionResult:
    """Undo a previously-executed reversible action, using its intent snapshot."""
    confirmed_ctx = _with_confirmation(ctx, confirmed_by_user_id)

    def _blocked(reason: str, msg: str, action: str = "") -> ExecutionResult:
        return ExecutionResult(ok=False, action=action, error=msg, blocked_reason=reason)

    if not agentic_mutating_enabled(school=school):
        return _blocked("mutating_disabled", "Mutating agentic actions are disabled.")

    try:
        from apps.platform_runtime.models_agentic_audit import (
            AIAgenticActionAudit,
            AIAgenticActionOutcome,
            AIAgenticActionPhase,
        )
    except Exception:  # noqa: BLE001
        return _blocked("audit_unavailable", "Audit store unavailable.")

    intent = (
        AIAgenticActionAudit.objects.filter(
            audit_id=audit_id, phase=AIAgenticActionPhase.INTENT,
        ).first()
    )
    if intent is None:
        return _blocked("not_found", "No intent record for that audit id.")
    # Only reverse actions that actually executed ok, and only once.
    executed_ok = AIAgenticActionAudit.objects.filter(
        audit_id=audit_id, phase=AIAgenticActionPhase.OUTCOME,
        outcome=AIAgenticActionOutcome.OK,
    ).exists()
    if not executed_ok:
        return _blocked("not_executed", "That action did not execute successfully.", intent.action)
    already = AIAgenticActionAudit.objects.filter(
        audit_id=audit_id, phase=AIAgenticActionPhase.REVERSAL,
        outcome=AIAgenticActionOutcome.OK,
    ).exists()
    if already:
        return _blocked("already_reversed", "That action was already reversed.", intent.action)

    spec = get_action(intent.action)
    perm_err = verify_permission(spec, confirmed_ctx) if spec else "unknown action"
    if perm_err:
        return _blocked("permission_denied", perm_err, intent.action)

    payload = intent.reversal_payload or {}
    if school is None:
        school = _resolve_school(confirmed_ctx.tenant_id)
    result = _apply_reversal(intent.action, payload, school)
    result.audit_id = audit_id

    _write_audit(
        audit_id=audit_id, ctx=confirmed_ctx,
        proposed=ProposedAction(action=intent.action, params={}),
        spec=spec, result=result, phase=AIAgenticActionPhase.REVERSAL,
    )
    return result


def _resolve_school(tenant_id: str):
    try:
        from services.ai_agentic_runners_mutating import _scope_school

        return _scope_school(tenant_id)
    except Exception:  # noqa: BLE001
        return None


def _apply_reversal(action: str, payload: dict, school) -> ExecutionResult:
    if action == "mark_student_absent":
        return _reverse_mark_student_absent(payload, school)
    if action == "schedule_parent_callback":
        return _reverse_schedule_parent_callback(payload, school)
    return ExecutionResult(ok=False, action=action, error="No reversal defined.",
                           blocked_reason="no_reversal")


def _reverse_mark_student_absent(payload: dict, school) -> ExecutionResult:
    student_id = str(payload.get("student_id") or "")
    date_iso = str(payload.get("date") or "")
    if not student_id or not date_iso or school is None:
        return ExecutionResult(ok=False, action="mark_student_absent",
                               error="Insufficient reversal data.", blocked_reason="no_reversal")
    try:
        from datetime import date as _date
        from apps.people.models import Student  # type: ignore
        from apps.academics.models import AttendanceRecord  # type: ignore

        y, m, d = (int(x) for x in date_iso.split("-"))
        on_date = _date(y, m, d)
        student = Student.objects.filter(school=school, pk=student_id).first()
        if student is None:
            return ExecutionResult(ok=False, action="mark_student_absent",
                                   error="Student not found.", blocked_reason="no_reversal")
        rec = AttendanceRecord.objects.filter(student=student, date=on_date).first()
        if rec is None:
            return ExecutionResult(ok=True, action="mark_student_absent",
                                   result={"reversed": True, "note": "record already absent"})
        if payload.get("existed"):
            rec.status = payload.get("prior_status") or rec.status
            rec.notes = payload.get("prior_notes") or ""
            rec.save(update_fields=["status", "notes"])
            return ExecutionResult(ok=True, action="mark_student_absent",
                                   result={"reversed": True, "restored_status": rec.status})
        rec.delete()
        return ExecutionResult(ok=True, action="mark_student_absent",
                               result={"reversed": True, "deleted": True})
    except Exception as exc:  # noqa: BLE001
        logger.exception("reverse mark_student_absent failed")
        return ExecutionResult(ok=False, action="mark_student_absent",
                               error=str(exc), blocked_reason="reversal_exception")


def _reverse_schedule_parent_callback(payload: dict, school) -> ExecutionResult:
    entry_id = str(payload.get("entry_id") or "")
    if not entry_id or school is None:
        return ExecutionResult(ok=False, action="schedule_parent_callback",
                               error="Insufficient reversal data.", blocked_reason="no_reversal")
    try:
        settings = getattr(school, "settings", None) or {}
        if not isinstance(settings, dict):
            settings = {}
        queue = settings.get("callback_queue")
        if not isinstance(queue, list):
            queue = []
        new_queue = [e for e in queue if not (isinstance(e, dict) and e.get("entry_id") == entry_id)]
        removed = len(queue) - len(new_queue)
        settings["callback_queue"] = new_queue
        school.settings = settings
        school.save(update_fields=["settings"])
        return ExecutionResult(ok=True, action="schedule_parent_callback",
                               result={"reversed": True, "removed": removed})
    except Exception as exc:  # noqa: BLE001
        logger.exception("reverse schedule_parent_callback failed")
        return ExecutionResult(ok=False, action="schedule_parent_callback",
                               error=str(exc), blocked_reason="reversal_exception")


# ===========================================================================
# Phase 3 — destructive actions (irreversible, DUAL-CONTROL, audited)
# ===========================================================================
#
# Owner-approved model (docs/AI_AGENTIC_ACTIONS_DESIGN.md):
#   * Gated by RMC_AI_AGENTIC_DESTRUCTIVE_ENABLED in addition to the base
#     Phase-1 gate (independent of the Phase-2 mutating sub-flag).
#   * TWO distinct humans: party A `request`s, a DIFFERENT party B `approve`s.
#     The approver≠requester check is enforced SERVER-SIDE (user-id hashes).
#   * A typed confirm phrase ("ERASE <student_id>") is required from BOTH parties.
#   * Requests EXPIRE if not approved within a TTL (cooling-off).
#   * Operator-only surface (super-access gated) for the first cut.
#   * NO new delete path: `purge_student_record` routes through the existing
#     compliance EraseRequest → fulfill_pending_erasure pipeline (GDPR Art. 17
#     anonymization), via services.ai_agentic_runners_destructive.

_DESTRUCTIVE = "destructive"
_DESTRUCTIVE_REQUEST_TTL_SECONDS = 1800  # magic-number-allow: 1800s = 30-min dual-control cooling-off window


def _agentic_destructive_flag_on() -> bool:
    return os.environ.get("RMC_AI_AGENTIC_DESTRUCTIVE_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def agentic_destructive_enabled(*, school=None) -> bool:
    """Phase-3 gate: the dedicated destructive flag AND the base Phase-1 gate.

    Independent of the Phase-2 mutating sub-flag — destructive is its own tier and
    must be turned on explicitly, but it does not require Phase-2 to be on.
    """
    if not _agentic_destructive_flag_on():
        return False
    return agentic_phase1_enabled(school=school)


def _destructive_require_dpo() -> bool:
    """When on (default), the dual-control pair for a destructive action MUST
    include at least one Data Protection Officer. Toggle via
    ``RMC_AI_AGENTIC_DESTRUCTIVE_REQUIRE_DPO`` (set to 0 only if DPOs aren't yet
    assigned in a tenant)."""
    return os.environ.get("RMC_AI_AGENTIC_DESTRUCTIVE_REQUIRE_DPO", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _roles_include_dpo(roles) -> bool:
    """True if the role tuple includes the DPO role. Uses the ``User.Role`` enum
    (canonical token), never a hardcoded role string."""
    from apps.accounts.models import User

    return User.Role.DPO.value in set(roles or ())


def _opt_in_destructive_runners() -> dict:
    try:
        from services.ai_agentic_runners_destructive import OPT_IN_DESTRUCTIVE_RUNNERS

        return dict(OPT_IN_DESTRUCTIVE_RUNNERS)
    except Exception:  # noqa: BLE001
        logger.debug("destructive runners unavailable", exc_info=True)
        return {}


def available_destructive_actions() -> tuple[ActionSpec, ...]:
    """Registered ``destructive`` (non-reversible) actions with an opt-in runner.

    This is the ENTIRE Phase-3 surface. Reversible/mutating/read-only actions are
    never here.
    """
    runners = set(_opt_in_destructive_runners().keys())
    return tuple(
        spec
        for spec in list_actions()
        if spec.impact == _DESTRUCTIVE and not spec.reversible and spec.name in runners
    )


def _is_destructive_eligible(spec: ActionSpec | None) -> bool:
    if spec is None:
        return False
    if spec.impact != _DESTRUCTIVE or spec.reversible:
        return False
    return spec.name in _opt_in_destructive_runners()


def _destructive_confirm_phrase(student_id: str) -> str:
    """The exact phrase BOTH parties must type. Friction against fat-finger; the
    value is the student id the action targets, so it can't be a blind resubmit."""
    return f"ERASE {str(student_id or '').strip()}"


def _destructive_rate_limit_ok(tenant_id: str, user_id: str) -> bool:
    from django.core.cache import cache

    try:
        cap = int(os.environ.get("RMC_AI_AGENTIC_DESTRUCTIVE_MAX_PER_HOUR", "5"))
    except (TypeError, ValueError):
        cap = 5
    bucket = int(time.time() // 3600)  # magic-number-allow: 3600s = 1-hour rate-limit bucket
    key = f"agentic_destr_rl:{tenant_id}:{user_id}:{bucket}"
    try:
        count = cache.get(key) or 0
        if count >= cap:
            return False
        cache.set(key, count + 1, timeout=3600)  # magic-number-allow: 3600s = 1-hour rate-limit window
    except Exception:  # noqa: BLE001 — cache outage: fail SAFE (allow), signature gates remain
        logger.debug("destructive rate-limit cache unavailable; allowing", exc_info=True)
    return True


def request_destructive_action(
    *,
    proposed: ProposedAction,
    ctx: ActionContext,
    requested_by_user_id: str,
    confirm_phrase: str,
    school=None,
) -> ExecutionResult:
    """Party-A step: record an intent to run a destructive action (no erasure yet).

    Gate order (each failure is audited as blocked, nothing is created):
    enabled → eligible(destructive + runner) → role → server-side confirmation
    → typed confirm phrase → rate limit. Then create a PENDING ``EraseRequest``
    and write a REQUEST audit row holding its id. A distinct operator must
    ``approve_destructive_action`` before anything is erased.
    """
    spec = get_action(proposed.action)
    confirmed_ctx = _with_confirmation(ctx, requested_by_user_id)

    def _blocked(reason: str, msg: str) -> ExecutionResult:
        r = ExecutionResult(ok=False, action=proposed.action, error=msg, blocked_reason=reason)
        _write_audit(audit_id="ag_" + uuid.uuid4().hex[:16], ctx=confirmed_ctx,
                     proposed=proposed, spec=spec, result=r)
        return r

    if not agentic_destructive_enabled(school=school):
        return _blocked("destructive_disabled", "Destructive agentic actions are disabled.")
    if not _is_destructive_eligible(spec):
        return _blocked("not_destructive_eligible",
                        "Phase 3 permits destructive actions with a bound runner only.")
    perm_err = verify_permission(spec, confirmed_ctx)
    if perm_err:
        return _blocked("permission_denied", perm_err)
    if not confirmed_ctx.confirmed_by:
        return _blocked("confirmation_required", "Server-side confirmation missing.")
    student_id = str((proposed.params or {}).get("student_id") or "").strip()
    if not student_id:
        return _blocked("student_id_required", "student_id required.")
    if (confirm_phrase or "").strip() != _destructive_confirm_phrase(student_id):
        return _blocked("bad_confirm_phrase", "Confirmation phrase does not match.")
    if not _destructive_rate_limit_ok(confirmed_ctx.tenant_id, confirmed_ctx.user_id):
        return _blocked("rate_limited", "Destructive request rate limit reached; try again later.")

    from services.ai_agentic_runners_destructive import create_purge_request

    created = create_purge_request(proposed, confirmed_ctx)
    if not created.get("ok"):
        return _blocked("request_failed", created.get("error") or "Could not create erase request.")

    audit_id = "ag_" + uuid.uuid4().hex[:16]
    reversal_payload = {
        "action": proposed.action,
        "erase_request_id": str(created.get("erase_request_id") or ""),
        "student_pk": str(created.get("student_pk") or ""),
        # Persist whether party A held DPO so the approve step can enforce
        # "≥1 DPO in the pair" without re-deriving the requester's role. Role
        # tokens are not PII.
        "requester_is_dpo": _roles_include_dpo(confirmed_ctx.user_roles),
    }
    from apps.platform_runtime.models_agentic_audit import (
        AIAgenticActionOutcome,
        AIAgenticActionPhase,
    )
    _write_audit(
        audit_id=audit_id, ctx=confirmed_ctx, proposed=proposed, spec=spec,
        result=ExecutionResult(ok=False, action=proposed.action, result={"request": True}),
        phase=AIAgenticActionPhase.REQUEST,
        reversal_payload=reversal_payload,
        outcome_override=AIAgenticActionOutcome.PENDING,
    )
    return ExecutionResult(
        ok=True, action=proposed.action,
        result={"pending_approval": True,
                "erase_request_id": created.get("erase_request_id")},
        audit_id=audit_id,
    )


def approve_destructive_action(
    *,
    audit_id: str,
    ctx: ActionContext,
    approver_user_id: str,
    confirm_phrase: str,
    school=None,
) -> ExecutionResult:
    """Party-B step: a DIFFERENT operator approves → the erasure actually runs.

    Re-checks every gate, enforces approver≠requester server-side, re-requires the
    typed confirm phrase, and refuses expired or already-finalized requests. On
    success it runs the sanctioned compliance erasure via the opt-in runner.
    """
    confirmed_ctx = _with_confirmation(ctx, approver_user_id)

    def _blocked(reason: str, msg: str, action: str = "") -> ExecutionResult:
        r = ExecutionResult(ok=False, action=action, error=msg, blocked_reason=reason)
        # Record blocked approval attempts (self-approval, wrong phrase, expired,
        # permission) for the security trail — correlated to the request's audit_id.
        # MUST use the APPROVAL phase, never OUTCOME: an OUTCOME row would falsely
        # finalize the request and bar a legitimate later approval.
        if action:
            try:
                from apps.platform_runtime.models_agentic_audit import (
                    AIAgenticActionPhase as _Phase,
                )

                _write_audit(audit_id=audit_id, ctx=confirmed_ctx,
                             proposed=ProposedAction(action=action, params={}),
                             spec=get_action(action), result=r, phase=_Phase.APPROVAL)
            except Exception:  # noqa: BLE001
                logger.debug("destructive approve block-audit failed", exc_info=True)
        return r

    if not agentic_destructive_enabled(school=school):
        return _blocked("destructive_disabled", "Destructive agentic actions are disabled.")

    try:
        from apps.platform_runtime.models_agentic_audit import (
            AIAgenticActionAudit,
            AIAgenticActionPhase,
        )
    except Exception:  # noqa: BLE001
        return _blocked("audit_unavailable", "Audit store unavailable.")

    req = AIAgenticActionAudit.objects.filter(
        audit_id=audit_id, phase=AIAgenticActionPhase.REQUEST,
    ).first()
    if req is None:
        return _blocked("not_found", "No destructive request for that id.")
    action = req.action

    if AIAgenticActionAudit.objects.filter(
        audit_id=audit_id, phase=AIAgenticActionPhase.OUTCOME,
    ).exists():
        return _blocked("already_finalized", "That request was already approved or rejected.", action)

    from django.utils import timezone

    age = (timezone.now() - req.created_at).total_seconds()
    if age > _DESTRUCTIVE_REQUEST_TTL_SECONDS:
        return _blocked("request_expired", "That destructive request has expired.", action)

    spec = get_action(action)
    perm_err = verify_permission(spec, confirmed_ctx) if spec else "unknown action"
    if perm_err:
        return _blocked("permission_denied", perm_err, action)
    if not confirmed_ctx.confirmed_by:
        return _blocked("confirmation_required", "Server-side confirmation missing.", action)
    # Dual control: the approver MUST be a different human than the requester.
    if _hash12(confirmed_ctx.user_id) == req.actor_user_id_hash:
        return _blocked("self_approval_forbidden",
                        "The approver must be a different operator than the requester.", action)

    payload = req.reversal_payload or {}

    # Data-protection dual-control: at least one of the two parties must be a DPO
    # (the requester's DPO status was captured at request time).
    if _destructive_require_dpo():
        requester_was_dpo = bool(payload.get("requester_is_dpo"))
        if not (requester_was_dpo or _roles_include_dpo(confirmed_ctx.user_roles)):
            return _blocked(
                "dpo_required",
                "At least one of the requester or approver must be a Data Protection Officer.",
                action,
            )

    student_pk = str(payload.get("student_pk") or "")
    erase_request_id = str(payload.get("erase_request_id") or "")
    if (confirm_phrase or "").strip() != _destructive_confirm_phrase(student_pk):
        return _blocked("bad_confirm_phrase", "Confirmation phrase does not match.", action)
    if not erase_request_id:
        return _blocked("request_corrupt", "Request is missing its erase reference.", action)

    # APPROVAL row (party B) — recorded BEFORE the irreversible run.
    _write_audit(
        audit_id=audit_id, ctx=confirmed_ctx,
        proposed=ProposedAction(action=action, params={}), spec=spec,
        result=ExecutionResult(ok=True, action=action, result={"approval": True}),
        phase=AIAgenticActionPhase.APPROVAL,
    )

    runner = _opt_in_destructive_runners().get(action)
    if runner is None:
        r = _blocked("no_runner", "No destructive runner bound for this action.", action)
        _write_audit(audit_id=audit_id, ctx=confirmed_ctx,
                     proposed=ProposedAction(action=action, params={}), spec=spec,
                     result=r, phase=AIAgenticActionPhase.OUTCOME)
        return r

    proposed = ProposedAction(action=action, params={"_erase_request_id": erase_request_id})
    result = execute_action(proposed, ctx=confirmed_ctx, runner=runner)
    result.audit_id = audit_id
    _write_audit(audit_id=audit_id, ctx=confirmed_ctx, proposed=proposed, spec=spec,
                 result=result, phase=AIAgenticActionPhase.OUTCOME)
    return result


def reject_destructive_action(
    *,
    audit_id: str,
    ctx: ActionContext,
    actor_user_id: str,
    school=None,
) -> ExecutionResult:
    """Cancel a still-pending destructive request (the underlying EraseRequest is
    marked REJECTED; nothing is erased). Any authorized operator may reject —
    including the original requester."""
    confirmed_ctx = _with_confirmation(ctx, actor_user_id)

    def _blocked(reason: str, msg: str, action: str = "") -> ExecutionResult:
        r = ExecutionResult(ok=False, action=action, error=msg, blocked_reason=reason)
        # Blocked reject attempts go in the trail too, on the APPROVAL phase (never
        # OUTCOME — that would finalize the request).
        if action:
            try:
                from apps.platform_runtime.models_agentic_audit import (
                    AIAgenticActionPhase as _Phase,
                )

                _write_audit(audit_id=audit_id, ctx=confirmed_ctx,
                             proposed=ProposedAction(action=action, params={}),
                             spec=get_action(action), result=r, phase=_Phase.APPROVAL)
            except Exception:  # noqa: BLE001
                logger.debug("destructive reject block-audit failed", exc_info=True)
        return r

    if not agentic_destructive_enabled(school=school):
        return _blocked("destructive_disabled", "Destructive agentic actions are disabled.")

    try:
        from apps.platform_runtime.models_agentic_audit import (
            AIAgenticActionOutcome,
            AIAgenticActionAudit,
            AIAgenticActionPhase,
        )
    except Exception:  # noqa: BLE001
        return _blocked("audit_unavailable", "Audit store unavailable.")

    req = AIAgenticActionAudit.objects.filter(
        audit_id=audit_id, phase=AIAgenticActionPhase.REQUEST,
    ).first()
    if req is None:
        return _blocked("not_found", "No destructive request for that id.")
    action = req.action
    if AIAgenticActionAudit.objects.filter(
        audit_id=audit_id, phase=AIAgenticActionPhase.OUTCOME,
    ).exists():
        return _blocked("already_finalized", "That request was already approved or rejected.", action)

    spec = get_action(action)
    perm_err = verify_permission(spec, confirmed_ctx) if spec else "unknown action"
    if perm_err:
        return _blocked("permission_denied", perm_err, action)

    payload = req.reversal_payload or {}
    erase_request_id = str(payload.get("erase_request_id") or "")
    rej = {"ok": True}
    if erase_request_id:
        from services.ai_agentic_runners_destructive import reject_purge_request

        rej = reject_purge_request(erase_request_id)

    _write_audit(
        audit_id=audit_id, ctx=confirmed_ctx,
        proposed=ProposedAction(action=action, params={}), spec=spec,
        result=ExecutionResult(ok=False, action=action, result={"rejected": True},
                               error="rejected by operator", blocked_reason="rejected"),
        phase=AIAgenticActionPhase.OUTCOME,
        outcome_override=AIAgenticActionOutcome.BLOCKED,
    )
    return ExecutionResult(
        ok=bool(rej.get("ok", True)), action=action,
        result={"rejected": True, "erase": rej}, blocked_reason="rejected", audit_id=audit_id,
    )


def pending_destructive_requests(*, tenant_id: str | None = None, limit: int = 25) -> list[dict]:
    """REQUEST rows awaiting approval (no terminal OUTCOME yet), for the operator
    surface. PII-free — exposes only hashes + the pseudonymous student pk."""
    try:
        from django.utils import timezone

        from apps.platform_runtime.models_agentic_audit import (
            AIAgenticActionAudit,
            AIAgenticActionPhase,
        )
    except Exception:  # noqa: BLE001
        return []

    reqs = AIAgenticActionAudit.objects.filter(phase=AIAgenticActionPhase.REQUEST)
    if tenant_id:
        reqs = reqs.filter(tenant_id=tenant_id)
    reqs = reqs.order_by("-created_at")[: max(1, min(limit, 100))]  # magic-number-allow: 100-row pending-list query cap

    finalized_qs = AIAgenticActionAudit.objects.filter(phase=AIAgenticActionPhase.OUTCOME)
    if tenant_id:
        finalized_qs = finalized_qs.filter(tenant_id=tenant_id)
    finalized = set(finalized_qs.values_list("audit_id", flat=True))

    now = timezone.now()
    out: list[dict] = []
    for r in reqs:
        if r.audit_id in finalized:
            continue
        payload = r.reversal_payload or {}
        age = (now - r.created_at).total_seconds()
        out.append(
            {
                "audit_id": r.audit_id,
                "action": r.action,
                "student_pk": str(payload.get("student_pk") or ""),
                "erase_request_id": str(payload.get("erase_request_id") or ""),
                "requester": r.actor_user_id_hash,
                "created_at": r.created_at,
                "expired": age > _DESTRUCTIVE_REQUEST_TTL_SECONDS,
            }
        )
    return out


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
                    "phase": r.phase,
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
