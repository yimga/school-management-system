"""Orchestrate multi-step workflow healing for Flight Deck operator actions."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.workflow_error_classifier import classify_workflow_run
from apps.platform_runtime.workflow_healing_chains import (
    chain_indicates_async_job,
    merge_operator_kind,
)
from apps.platform_runtime.workflow_healing_session import (
    start_healing_session,
    update_healing_session,
)
from apps.platform_runtime.workflow_fix_handlers import (
    apply_auto_fix_kind,
    auto_fix_capability,
    auto_fix_kind_is_executable,
)


def resolve_healing_chain(run: Any, *, kind: str) -> list[str]:
    """Build ordered fix chain for any workflow run."""

    fingerprint = classify_workflow_run(run)
    chain = list(fingerprint.recommended_chain or [])
    chain = merge_operator_kind(chain=chain, kind=kind)
    if not chain:
        remediation = getattr(run, "suggested_remediation", None) or {}
        fallback = str(remediation.get("auto_fix_kind") or "").strip()
        if fallback and auto_fix_kind_is_executable(fallback):
            chain = [fallback]
    return _dedupe_chain(chain)


def healing_supported_for_run(run: Any, *, kind: str = "apply_fix") -> bool:
    return bool(resolve_healing_chain(run, kind=kind))


def _dedupe_chain(chain: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in chain:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _step_label(kind: str) -> str:
    cap = auto_fix_capability(kind)
    return str(cap.get("label") or kind.replace("_", " ").title())


def _should_skip_step(run: Any, kind: str) -> str | None:
    if kind == "clear_stale_lock":
        payload = getattr(run, "payload_summary", None) or {}
        for key in ("lock_key", "cache_lock_key", "stale_lock_key"):
            if payload.get(key):
                return None
        return "no_lock_key_in_payload"
    if kind == "cancel_duplicate_run":
        # Always attempt — handler returns not_found when none exist (treat as skip).
        return None
    if kind in ("repair_tenant_schema_drift", "run_tenant_migrations"):
        schema = str(
            getattr(run, "tenant_schema", "")
            or (getattr(run, "payload_summary", None) or {}).get("tenant_schema")
            or ""
        ).strip()
        if not schema:
            return "missing_tenant_schema"
    return None


def _classify_run(run: Any, *, request: Any | None) -> Any:
    from apps.platform_runtime.workflow_healing_ai import enrich_fingerprint_with_ai

    fingerprint = classify_workflow_run(run)
    return enrich_fingerprint_with_ai(run=run, fingerprint=fingerprint, request=request)


def apply_healing_for_run(
    *,
    run: Any,
    kind: str,
    actor_user_id: str = "",
    request: Any | None = None,
) -> dict[str, Any]:
    """Classify, start session, execute fix chain, return JSON for Flight Deck."""

    fingerprint = _classify_run(run, request=request)
    chain = resolve_healing_chain(run, kind=kind)
    if not chain:
        return {
            "ok": False,
            "reason": "empty_healing_chain",
            "fingerprint": fingerprint.as_dict(),
        }

    session = start_healing_session(
        run=run,
        chain=chain,
        fingerprint=fingerprint.as_dict(),
        actor_user_id=actor_user_id,
    )
    update_healing_session(
        run,
        phase="preflight_fix",
        current_step_label="Running automated fix plan…",
        log_line=f"Plan: {' → '.join(chain)}",
    )

    chain_results: list[dict[str, Any]] = []
    last_result: dict[str, Any] = {"ok": False, "reason": "no_steps_ran"}

    for index, step_kind in enumerate(chain):
        skip_reason = _should_skip_step(run, step_kind)
        if skip_reason:
            entry = {"kind": step_kind, "ok": True, "skipped": True, "reason": skip_reason}
            chain_results.append(entry)
            update_healing_session(
                run,
                log_line=f"Skipped {_step_label(step_kind)} ({skip_reason})",
                chain_result=entry,
            )
            continue

        defer_stamp = (index < len(chain) - 1) or bool(session.get("session_id"))
        update_healing_session(
            run,
            progress_percent=min(70, 20 + int(50 * (index + 1) / max(len(chain), 1))),
            current_step_label=_step_label(step_kind),
            log_line=f"Running {_step_label(step_kind)}…",
        )

        step_result = apply_auto_fix_kind(
            run=run,
            kind=step_kind,
            defer_remediation_stamp=defer_stamp,
        )
        entry = {
            "kind": step_kind,
            "ok": bool(step_result.get("ok")),
            "reason": step_result.get("reason", ""),
        }
        chain_results.append(entry)
        update_healing_session(run, chain_result=entry)

        if not step_result.get("ok"):
            update_healing_session(
                run,
                phase="failed",
                current_step_label=f"{_step_label(step_kind)} failed",
                log_line=str(step_result.get("reason") or "Step failed")[:500],
            )
            return {
                "ok": False,
                "reason": step_result.get("reason") or "chain_step_failed",
                "failed_kind": step_kind,
                "healing_session": _session_snapshot(run),
                "fingerprint": fingerprint.as_dict(),
                "chain_results": chain_results,
                "refresh_deck": True,
                "healing_poll_ms": 2500,
            }
        last_result = step_result

    async_job = chain_indicates_async_job(chain)
    update_healing_session(
        run,
        phase="requeue_queued" if async_job else "succeeded",
        progress_percent=85 if async_job else 100,
        current_step_label=(
            "Background job queued — watch active runs"
            if async_job
            else "Fix complete"
        ),
        log_line="Healing chain finished successfully.",
    )
    if not async_job:
        update_healing_session(run, phase="succeeded", progress_percent=100)

    return {
        "ok": True,
        "applied": "healing_chain",
        "chain": chain,
        "chain_results": chain_results,
        "healing_session": _session_snapshot(run),
        "fingerprint": fingerprint.as_dict(),
        "refresh_deck": True,
        "healing_poll_ms": 2500,
        "operator_message": (
            "Self-healing launched. Progress updates live on this card."
        ),
        "remediated_run_id": getattr(run, "pk", None),
        **{
            k: v
            for k, v in last_result.items()
            if k not in ("ok", "reason", "applied")
        },
    }


def _session_snapshot(run: Any) -> dict[str, Any]:
    from apps.platform_runtime.workflow_healing_session import healing_session_from_run

    return healing_session_from_run(run)


def healing_status_for_run(run: Any) -> dict[str, Any]:
    fingerprint = classify_workflow_run(run)
    session = _session_snapshot(run)
    return {
        "run_id": getattr(run, "pk", None),
        "healing_session": session,
        "error_fingerprint": fingerprint.as_dict(),
        "healing_active": bool(session) and str(session.get("phase")) not in (
            "succeeded",
            "failed",
            "cancelled",
            "",
        ),
    }
