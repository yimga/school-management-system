"""Idempotent auto-fix handlers for Workflow Progress Bus."""

from __future__ import annotations

from io import StringIO
from typing import Any

from django.core.management import call_command
from django.utils import timezone

_REMEDIATED_PAYLOAD_KEY = "workflow_fix_remediation"

AUTO_FIX_HANDLER_CATALOG: dict[str, dict[str, Any]] = {
    "requeue_provision": {
        "label": "Requeue provisioning",
        "mode": "execute",
        "confidence": "high",
        "requires_network": True,
        "description": "Launches the idempotent school provisioning task again.",
    },
    "resend_welcome": {
        "label": "Resend welcome email",
        "mode": "execute",
        "confidence": "high",
        "requires_network": True,
        "description": "Sends the tenant welcome email again.",
    },
    "retry_dns_sync": {
        "label": "Retry DNS sync",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": True,
        "description": "Re-syncs runtime domains and retries DNS provisioning.",
    },
    "repair_tenant_schema_drift": {
        "label": "Repair schema drift",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": False,
        "description": "Runs tenant schema drift healing in apply mode.",
    },
    "run_tenant_migrations": {
        "label": "Run tenant migrations",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": False,
        "description": "Runs tenant migrations through the existing management command.",
    },
    "mark_superseded": {
        "label": "Mark superseded",
        "mode": "execute",
        "confidence": "high",
        "requires_network": False,
        "description": "Moves the old row out of the unresolved deck after replacement work exists.",
    },
    "retry_once_with_backoff": {
        "label": "Retry with backoff",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": True,
        "description": "Marks the run for retry and records retry metadata.",
    },
    "retry_after_rate_limit": {
        "label": "Retry after rate limit",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": True,
        "description": "Marks the run for a rate-limit-safe retry.",
    },
    "refresh_oauth_token_and_retry": {
        "label": "Refresh token and retry",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": True,
        "description": "Marks the run for retry after credential refresh.",
    },
    "suggest_alternate_slug": {
        "label": "Suggest alternate slug",
        "mode": "diagnostic",
        "confidence": "medium",
        "requires_network": False,
        "description": "Computes slug alternatives; no automatic database mutation.",
    },
    "resume_from_checkpoint": {
        "label": "Resume from checkpoint",
        "mode": "diagnostic",
        "confidence": "unknown",
        "requires_network": False,
        "description": "No deterministic resume handler is registered yet.",
    },
    "retry_failed_step": {
        "label": "Retry failed step",
        "mode": "diagnostic",
        "confidence": "unknown",
        "requires_network": False,
        "description": "No per-step replay handler is registered yet.",
    },
    "replay_webhook": {
        "label": "Replay webhook",
        "mode": "diagnostic",
        "confidence": "unknown",
        "requires_network": True,
        "description": "Webhook source metadata is required before replay.",
    },
    "clear_stale_lock": {
        "label": "Clear stale lock",
        "mode": "diagnostic",
        "confidence": "unknown",
        "requires_network": False,
        "description": "Lock identity is required before automated unlock.",
    },
    "cancel_duplicate_run": {
        "label": "Cancel duplicate run",
        "mode": "diagnostic",
        "confidence": "unknown",
        "requires_network": False,
        "description": "Duplicate target selection must be confirmed in run detail.",
    },
    "open_diagnostic_detail": {
        "label": "Open AI diagnosis",
        "mode": "navigation",
        "confidence": "high",
        "requires_network": False,
        "description": "Opens the run detail with AI-ready context.",
    },
}


def auto_fix_capability(kind: str) -> dict[str, Any]:
    """Return public capability metadata for an auto-fix kind."""

    key = str(kind or "").strip()
    meta = dict(AUTO_FIX_HANDLER_CATALOG.get(key) or {})
    if not meta:
        return {
            "label": "Unsupported fix",
            "mode": "unsupported",
            "confidence": "unknown",
            "requires_network": False,
            "description": "No handler is registered for this auto_fix_kind.",
        }
    meta["kind"] = key
    return meta


def auto_fix_kind_is_executable(kind: str) -> bool:
    return auto_fix_capability(kind).get("mode") == "execute"


def workflow_run_remediation_stamp(run: Any) -> dict[str, Any]:
    """Return the latest fix stamp for a run, if a fix already superseded it."""

    for source in (
        getattr(run, "payload_summary", None),
        getattr(run, "suggested_remediation", None),
    ):
        if not isinstance(source, dict):
            continue
        stamp = source.get(_REMEDIATED_PAYLOAD_KEY) or source.get("applied_fix")
        if isinstance(stamp, dict) and stamp.get("applied_at"):
            return stamp
    return {}


def workflow_run_is_remediated(run: Any) -> bool:
    """True when a terminal/stuck row has already launched a repair action."""

    return bool(workflow_run_remediation_stamp(run))


def _mark_run_remediated(
    *,
    run: Any,
    kind: str,
    result: dict[str, Any],
    status: str = "",
) -> dict[str, Any]:
    """Stamp the original run after a real fix is launched.

    The old row remains auditable, but the Flight Deck can stop presenting it as
    an unresolved red item while the newly queued workflow takes over.
    """

    if run is None or getattr(run, "pk", None) is None:
        return {}

    from apps.platform_runtime.models import WorkflowRun

    now = timezone.now()
    payload = dict(getattr(run, "payload_summary", None) or {})
    remediation = dict(getattr(run, "suggested_remediation", None) or {})
    stamp = {
        "kind": kind,
        "applied_at": now.isoformat(),
        "school_id": str(result.get("school_id") or getattr(run, "school_id", "") or ""),
        "result": {
            "ok": bool(result.get("ok")),
            "applied": str(result.get("applied") or kind),
        },
    }
    payload[_REMEDIATED_PAYLOAD_KEY] = stamp
    remediation[_REMEDIATED_PAYLOAD_KEY] = stamp
    remediation["auto_fix_available"] = False
    remediation["human_action"] = (
        "Fix launched. The original run is now superseded; watch the active run "
        "for live delivery."
    )
    update_fields: dict[str, Any] = {
        "payload_summary": payload,
        "suggested_remediation": remediation,
        "last_heartbeat_at": now,
    }
    if status:
        update_fields["status"] = status
        update_fields["ended_at"] = now
    WorkflowRun.objects.filter(pk=run.pk).update(**update_fields)  # tenant-isolation-allow: workflow-run-remediation-stamp-by-pk
    return stamp


def preview_auto_fix_kind(*, run: Any, kind: str) -> dict[str, Any]:
    """Shadow/dry-run: describe what apply would do without mutating the run."""

    capability = auto_fix_capability(kind)
    workflow_key = getattr(run, "workflow_key", "")
    payload = dict(getattr(run, "payload_summary", None) or {})

    if capability.get("mode") not in ("execute", "diagnostic", "navigation"):
        return {
            "ok": False,
            "dry_run": True,
            "reason": "unsupported_fix_kind",
            "kind": kind,
            "capability": capability,
        }

    if capability.get("mode") in ("diagnostic", "navigation"):
        return {
            "ok": True,
            "dry_run": True,
            "would_apply": "",
            "kind": kind,
            "capability": capability,
            "note": capability.get("description", "Open run detail for diagnosis."),
        }

    if kind == "suggest_alternate_slug":
        base = payload.get("slug") or workflow_key
        alternates = [f"{base}-2026", f"{base}-academy", f"{base}-school"]
        return {
            "ok": True,
            "dry_run": True,
            "would_apply": kind,
            "capability": capability,
            "alternates": alternates,
            "note": "No database changes in preview mode.",
        }

    if kind in ("retry_once_with_backoff", "retry_after_rate_limit", "refresh_oauth_token_and_retry"):
        return {
            "ok": True,
            "dry_run": True,
            "would_apply": kind,
            "would_set_status": "running",
            "current_status": getattr(run, "status", ""),
            "capability": capability,
            "note": "Would mark run running and stamp retry metadata in payload_summary.",
        }

    if kind in (
        "requeue_provision",
        "resend_welcome",
        "retry_dns_sync",
        "repair_tenant_schema_drift",
        "run_tenant_migrations",
        "mark_superseded",
    ):
        return {
            "ok": True,
            "dry_run": True,
            "would_apply": kind,
            "workflow_key": workflow_key,
            "capability": capability,
            "note": capability.get("description", "Owner-safe remediation."),
        }

    return {
        "ok": False,
        "dry_run": True,
        "reason": "unsupported_fix_kind",
        "kind": kind,
        "capability": capability,
    }


def apply_auto_fix_kind(*, run: Any, kind: str) -> dict[str, Any]:
    """Execute a supported ``auto_fix_kind``. Returns JSON-serializable result."""

    from apps.platform_runtime.models import WorkflowRun

    workflow_key = getattr(run, "workflow_key", "")
    payload = dict(getattr(run, "payload_summary", None) or {})
    capability = auto_fix_capability(kind)

    if capability.get("mode") != "execute":
        return {
            "ok": False,
            "reason": "diagnostic_only"
            if capability.get("mode") in ("diagnostic", "navigation")
            else "unsupported_fix_kind",
            "kind": kind,
            "capability": capability,
        }

    if kind == "suggest_alternate_slug":
        base = payload.get("slug") or workflow_key
        alternates = [f"{base}-2026", f"{base}-academy", f"{base}-school"]
        return {"ok": False, "reason": "diagnostic_only", "applied": kind, "alternates": alternates}

    if kind in ("retry_once_with_backoff", "retry_after_rate_limit", "refresh_oauth_token_and_retry"):
        WorkflowRun.objects.filter(pk=run.pk).update(  # tenant-isolation-allow: workflow-run-update-by-primary-key-row
            status="running",
            last_heartbeat_at=timezone.now(),
            payload_summary={
                **payload,
                "retry_requested_at": timezone.now().isoformat(),
                "retry_kind": kind,
            },
        )
        return {
            "ok": True,
            "applied": kind,
            "note": "Run marked for retry. Re-invoke the original action.",
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }

    if kind == "repair_tenant_schema_drift":
        tenant_schema = str(
            getattr(run, "tenant_schema", "") or payload.get("tenant_schema") or ""
        ).strip()
        if not tenant_schema:
            return {"ok": False, "reason": "missing_tenant_schema", "kind": kind}
        stdout = StringIO()
        stderr = StringIO()
        call_command(
            "heal_tenant_schema_drift",
            "--schema",
            tenant_schema,
            "--apply",
            stdout=stdout,
            stderr=stderr,
        )
        result = {
            "ok": True,
            "applied": kind,
            "tenant_schema": tenant_schema,
            "stdout": stdout.getvalue()[-1200:],
            "stderr": stderr.getvalue()[-1200:],
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        return result

    if kind == "run_tenant_migrations":
        stdout = StringIO()
        stderr = StringIO()
        call_command(
            "run_tenant_migrations",
            "--noinput",
            stdout=stdout,
            stderr=stderr,
        )
        result = {
            "ok": True,
            "applied": kind,
            "stdout": stdout.getvalue()[-1200:],
            "stderr": stderr.getvalue()[-1200:],
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        return result

    if kind == "mark_superseded":
        result = {
            "ok": True,
            "applied": kind,
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        status = "cancelled" if getattr(run, "status", "") in ("running", "stuck") else ""
        result["remediation"] = _mark_run_remediated(
            run=run,
            kind=kind,
            result=result,
            status=status,
        )
        return result

    if kind == "requeue_provision" and workflow_key == "tenant_school_provision":
        school_id = str(getattr(run, "school_id", "") or payload.get("school_id") or "")
        if not school_id:
            return {"ok": False, "reason": "missing_school_id", "kind": kind}
        from apps.schools.models import School
        from apps.schools.operator_school_lens import can_operator_requeue_provisioning
        from apps.schools.tasks import dispatch_provision_school

        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return {"ok": False, "reason": "school_not_found", "kind": kind}
        if not can_operator_requeue_provisioning(school):
            return {"ok": False, "reason": "requeue_not_allowed", "kind": kind}
        contact = str(payload.get("contact_email") or "").strip()
        dispatch_provision_school(school_id, contact_email=contact)
        result = {"ok": True, "applied": kind, "school_id": school_id}
        status = "cancelled" if getattr(run, "status", "") in ("running", "stuck") else ""
        result["remediation"] = _mark_run_remediated(
            run=run,
            kind=kind,
            result=result,
            status=status,
        )
        result["refresh_deck"] = True
        return result

    if kind == "resend_welcome" and workflow_key == "tenant_school_provision":
        school_id = str(getattr(run, "school_id", "") or payload.get("school_id") or "")
        if not school_id:
            return {"ok": False, "reason": "missing_school_id", "kind": kind}
        from apps.schools.models import School
        from apps.schools.welcome_email import send_welcome_email

        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return {"ok": False, "reason": "school_not_found", "kind": kind}
        contact = str(payload.get("contact_email") or "").strip()
        send_welcome_email(school, contact)
        result = {"ok": True, "applied": kind, "school_id": school_id}
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        result["refresh_deck"] = True
        return result

    if kind == "retry_dns_sync" and workflow_key == "tenant_school_provision":
        school_id = str(getattr(run, "school_id", "") or payload.get("school_id") or "")
        if not school_id:
            return {"ok": False, "reason": "missing_school_id", "kind": kind}
        from apps.schools.models import School
        from apps.schools.tasks import _provision_dns_record, sync_school_domains_to_runtime

        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return {"ok": False, "reason": "school_not_found", "kind": kind}
        try:
            sync_school_domains_to_runtime(school)
            _provision_dns_record(school)
        except (OSError, ConnectionError, AttributeError, TypeError, ValueError) as exc:
            return {"ok": False, "reason": str(exc)[:200], "kind": kind}
        result = {"ok": True, "applied": kind, "school_id": school_id}
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        result["refresh_deck"] = True
        return result

    return {
        "ok": False,
        "reason": "unsupported_fix_kind",
        "kind": kind,
        "capability": capability,
    }


# --- Stuck-run remediation (v4.04) ------------------------------------------
# A run the stuck-sweep just flagged is still "running" semantically (it never
# raised), so the failure-path remediation never fired and the card carries no
# action. Resolve a remediation here so the operator gets a one-click Retry and
# the unattended autopilot has a concrete target.

# Default auto-fix kind per workflow for a STUCK (not-yet-failed) run. Only
# workflows with a genuinely idempotent, owner-safe re-drive are listed; any
# other workflow gets an explain-only card (Cancel + visibility, no false
# "Apply" button).
STUCK_DEFAULT_FIX_BY_WORKFLOW = {
    "tenant_school_provision": "requeue_provision",
}


def resolve_stuck_remediation(*, run: Any) -> dict[str, Any]:
    """Build a ``suggested_remediation`` payload for a run the sweep marked stuck.

    For workflows with a known idempotent re-drive this enables the one-click
    Retry (Apply) button AND the unattended autopilot; otherwise it returns an
    explain-only card (``human_action`` set, ``auto_fix_available`` false) so the
    operator still gets context + a Cancel action without a misleading Apply.
    """

    workflow_key = getattr(run, "workflow_key", "") or ""
    kind = STUCK_DEFAULT_FIX_BY_WORKFLOW.get(workflow_key, "")
    if kind == "requeue_provision":
        return {
            "auto_fix_available": True,
            "auto_fix_kind": kind,
            "human_action": (
                "Provisioning has stalled past its expected time. Re-queue the "
                "job — it is idempotent and resumes safely."
            ),
            "reason": "stuck",
            "source": "stuck_sweep",
        }
    return {
        "auto_fix_available": False,
        "human_action": (
            "This workflow has stalled past its expected time. Review the run "
            "and cancel it or retry the originating action."
        ),
        "reason": "stuck",
        "source": "stuck_sweep",
    }
