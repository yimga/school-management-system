"""Operator action metadata for Workflow Flight Deck rows."""

from __future__ import annotations

from typing import Any

from django.urls import reverse


def _apply_fix_label(auto_fix_kind: str) -> str:
    from apps.platform_runtime.workflow_fix_handlers import auto_fix_capability

    capability_label = str(auto_fix_capability(auto_fix_kind).get("label") or "").strip()
    if capability_label:
        return capability_label
    labels = {
        "requeue_provision": "Requeue provisioning",
        "resend_welcome": "Resend welcome email",
        "retry_dns_sync": "Retry DNS sync",
        "retry_once_with_backoff": "Retry with backoff",
        "retry_after_rate_limit": "Retry after rate limit",
        "refresh_oauth_token_and_retry": "Refresh token & retry",
        "suggest_alternate_slug": "Suggest alternate slug",
    }
    return labels.get(auto_fix_kind, "Apply fix")


_PROVISION_SPECIFIC_FIXES = frozenset(
    {"suggest_alternate_slug", "resend_welcome", "retry_dns_sync"}
)
_RETRY_ONLY_FIXES = frozenset(
    {
        "retry_once_with_backoff",
        "retry_after_rate_limit",
        "refresh_oauth_token_and_retry",
    }
)


def _requeue_provision_remediation(rem: dict[str, Any]) -> dict[str, Any]:
    return {
        **rem,
        "verdict": rem.get("verdict") or "provision_operator_requeue",
        "remediation_key": rem.get("remediation_key") or "provisioning_step_failed",
        "human_action": rem.get("human_action")
        or (
            "School setup did not finish. Re-queue provisioning — the job is "
            "idempotent and resumes from the last safe checkpoint."
        ),
        "auto_fix_available": True,
        "auto_fix_kind": "requeue_provision",
        "suggested_next": "Use Requeue provisioning or Apply fix.",
    }


def _tenant_schema_step_remediation(rem: dict[str, Any], *, run: Any) -> dict[str, Any]:
    """Executable heal plan for a dead/stuck provision pinned at tenant_schema.

    Auto fix MUST mutate (repair drift → requeue), never leave "Diagnostic only".
    """

    step = str(getattr(run, "current_step_name", "") or "").strip()
    out = _requeue_provision_remediation(rem)
    if step == "tenant_schema":
        out.update(
            {
                "verdict": rem.get("verdict") or "tenant_schema_self_heal",
                "remediation_key": rem.get("remediation_key")
                or "tenant_schema_stalled",
                "human_action": (
                    "Campus workspace setup stalled while creating the tenant "
                    "database schema. Auto fix repairs schema drift, then "
                    "re-queues provisioning (idempotent)."
                ),
                "auto_fix_available": True,
                "auto_fix_kind": "requeue_provision",
                "healing_chain": [
                    "cancel_duplicate_run",
                    "repair_tenant_schema_drift",
                    "requeue_provision",
                ],
                "suggested_next": "Apply fix — cancel duplicates, repair schema, requeue.",
                "reason": rem.get("reason") or "tenant_schema_dead_running",
                "source": rem.get("source") or "effective_remediation",
            }
        )
    return out


def resolve_effective_remediation(run: Any) -> dict[str, Any]:
    """Remediation envelope used by Flight Deck UI and apply-fix handlers.

    Upgrades legacy failed/stuck provision rows that pre-date the requeue fallback
    so operators are not blocked by stale ``auto_fix_available: false`` in DB.
    Also replaces generic retry/backoff suggestions for provisioning with an
    explicit requeue — retry metadata alone does not restart the Celery job.

    Critical: a heartbeat-dead ``running`` row stuck at ``tenant_schema`` must
    still surface an *executable* auto-fix (not "Diagnostic only"). Liveness is
    judged by ``provision_workflow_run_is_live``, matching the watchdog.
    """

    rem = dict(getattr(run, "suggested_remediation", None) or {})
    workflow_key = getattr(run, "workflow_key", "") or ""
    status = (getattr(run, "status", "") or "").lower()

    if workflow_key == "tenant_school_provision":
        dead_running = False
        if status == "running":
            try:
                from apps.schools.provision_watchdog import (
                    provision_workflow_run_is_live,
                )

                dead_running = not provision_workflow_run_is_live(run)
            except Exception:
                # Fail open toward heal: no heartbeat proof ⇒ treat as dead.
                dead_running = getattr(run, "last_heartbeat_at", None) is None

        if status == "stuck" and not rem.get("auto_fix_kind"):
            from apps.platform_runtime.workflow_fix_handlers import (
                resolve_stuck_remediation,
            )

            base = resolve_stuck_remediation(run=run)
            return _tenant_schema_step_remediation(base, run=run)

        if dead_running:
            return _tenant_schema_step_remediation(rem, run=run)

        if status in ("failed", "stuck", "cancelled"):
            kind = str(rem.get("auto_fix_kind") or "").strip()
            if kind in _PROVISION_SPECIFIC_FIXES:
                return rem
            if (
                not rem.get("auto_fix_available")
                or kind in _RETRY_ONLY_FIXES
                or not kind
            ):
                return _tenant_schema_step_remediation(rem, run=run)
            if str(getattr(run, "current_step_name", "") or "").strip() == "tenant_schema":
                return _tenant_schema_step_remediation(rem, run=run)
    return rem


_ONLINE_ONLY_ACTION_KINDS = frozenset(
    {
        "apply_fix",
        "preview_fix",
        "bulk_apply_fix",
        "requeue_provision",
        "cancel",
        "clear_after_success",
    }
)


def _action_meta(kind: str, **fields: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        **fields,
        "requires_network": kind in _ONLINE_ONLY_ACTION_KINDS,
        "offline_hint": (
            "Requires network — retry when connected"
            if kind in _ONLINE_ONLY_ACTION_KINDS
            else ""
        ),
    }


def build_operator_actions(*, run: Any, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ordered operator actions for a workflow run row."""

    from apps.platform_runtime.workflow_fix_handlers import (
        auto_fix_capability,
        auto_fix_kind_is_executable,
        workflow_run_is_remediated,
    )

    actions: list[dict[str, Any]] = []
    status = (payload.get("status") or "").lower()
    workflow_key = payload.get("workflow_key") or ""
    school_id = str(payload.get("school_id") or "").strip()
    rem = payload.get("suggested_remediation") or {}
    auto_fix_kind = str(rem.get("auto_fix_kind") or "").strip()
    remediated = bool(run is not None and workflow_run_is_remediated(run))
    run_id = payload.get("id")
    detail_action: dict[str, Any] | None = None

    if run_id:
        try:
            detail_action = {
                "kind": "detail",
                "label": "View run detail",
                "href": reverse(
                    "platform_runtime:workflow_progress_run_detail",
                    args=[run_id],
                ),
                "primary": False,
                "capability": auto_fix_capability("open_diagnostic_detail"),
            }
        except Exception:
            detail_action = None

    if remediated:
        if detail_action:
            actions.append(detail_action)
        return actions

    if (
        rem.get("auto_fix_available")
        and auto_fix_kind
        and auto_fix_kind_is_executable(auto_fix_kind)
    ):
        capability = auto_fix_capability(auto_fix_kind)
        actions.append(
            _action_meta(
                "apply_fix",
                label=_apply_fix_label(auto_fix_kind),
                primary=True,
                capability=capability,
            )
        )
        actions.append(
            _action_meta(
                "preview_fix",
                label="Preview fix",
                primary=False,
                capability=capability,
            )
        )
    elif auto_fix_kind and detail_action:
        detail_action["label"] = "Open AI diagnosis"
        actions.append(detail_action)

    if workflow_key == "tenant_school_provision" and school_id:
        can_requeue = _can_requeue_provision(school_id)
        has_apply = any(item.get("kind") == "apply_fix" for item in actions)
        if can_requeue and not has_apply:
            actions.insert(
                0,
                _action_meta(
                    "requeue_provision",
                    label="Requeue provisioning",
                    primary=True,
                    capability=auto_fix_capability("requeue_provision"),
                ),
            )
        elif can_requeue and auto_fix_kind != "requeue_provision":
            actions.append(
                _action_meta(
                    "requeue_provision",
                    label="Requeue provisioning",
                    primary=False,
                    capability=auto_fix_capability("requeue_provision"),
                )
            )
        try:
            actions.append(
                {
                    "kind": "provision_queue",
                    "label": "Open provision queue",
                    "href": reverse("super:provision_queue"),
                    "primary": False,
                }
            )
            actions.append(
                {
                    "kind": "tenant_360",
                    "label": "Open Tenant 360",
                    "href": reverse("super:tenant_360", args=[school_id]),
                    "primary": False,
                }
            )
        except Exception:
            pass
        # Operator clear only after success proof — unfinished failures stay.
        try:
            from apps.platform_runtime.tasks import (
                provision_failure_clearable_after_success,
            )

            if run is not None and provision_failure_clearable_after_success(run):
                actions.insert(
                    0,
                    _action_meta(
                        "clear_after_success",
                        label="Clear from deck",
                        primary=True,
                        capability=auto_fix_capability("clear_after_success"),
                    ),
                )
        except Exception:
            pass

    if detail_action and not any(a.get("kind") == "detail" for a in actions):
        actions.append(detail_action)

    if status in ("running", "stuck", "degrading"):
        actions.append(
            _action_meta(
                "cancel",
                label="Cancel run",
                primary=False,
                capability=auto_fix_capability("mark_superseded"),
            )
        )

    return actions


def enrich_run_payload(serialized: dict[str, Any], *, run: Any | None = None) -> dict[str, Any]:
    """Augment a serialized workflow run for Flight Deck operator UI."""

    from apps.platform_runtime.workflow_fix_handlers import workflow_run_is_remediated
    from apps.platform_runtime.workflow_healing import healing_status_for_run
    from apps.platform_runtime.workflow_recovery_playbook import (
        recovery_strategy_for_workflow,
    )
    from apps.platform_runtime.workflow_status_taxonomy import (
        recovery_context_for_run,
        status_meta,
    )

    out = dict(serialized)
    remediated = bool(run is not None and workflow_run_is_remediated(run))
    if run is not None:
        out["suggested_remediation"] = resolve_effective_remediation(run)
        if getattr(run, "error_summary", None):
            out["error_summary"] = run.error_summary
        healing_status = healing_status_for_run(run)
        out["healing_session"] = healing_status.get("healing_session") or {}
        out["error_fingerprint"] = healing_status.get("error_fingerprint") or {}
        if healing_status.get("healing_active"):
            out["status_meta"] = status_meta("healing", remediated=remediated)
            out["display_status"] = out["status_meta"]["label"]
    else:
        out.setdefault("healing_session", {})
        out.setdefault("error_fingerprint", {})
    if not out.get("status_meta"):
        out["status_meta"] = status_meta(str(out.get("status") or ""), remediated=remediated)
        out["display_status"] = out["status_meta"]["label"]
    if remediated:
        out["recovery_state"] = "superseded"
    out["operator_actions"] = build_operator_actions(run=run, payload=out)
    out["recovery_strategy"] = recovery_strategy_for_workflow(
        str(out.get("workflow_key") or "")
    )
    out["copilot_recovery_context"] = recovery_context_for_run(
        out,
        action_count=len(out["operator_actions"]),
        remediated=remediated,
    )
    from apps.platform_runtime.workflow_attention_gateway import attach_attention_fields

    return attach_attention_fields(out, run=run)


def _can_requeue_provision(school_id: str) -> bool:
    try:
        from apps.schools.models import School
        from apps.schools.operator_school_lens import can_operator_requeue_provisioning

        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return False
        return bool(can_operator_requeue_provisioning(school))
    except Exception:
        return False
