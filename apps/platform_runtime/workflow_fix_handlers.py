"""Idempotent auto-fix handlers for Workflow Progress Bus."""

from __future__ import annotations

from typing import Any

from django.utils import timezone


def preview_auto_fix_kind(*, run: Any, kind: str) -> dict[str, Any]:
    """Shadow/dry-run: describe what apply would do without mutating the run."""

    workflow_key = getattr(run, "workflow_key", "")
    payload = dict(getattr(run, "payload_summary", None) or {})

    if kind == "suggest_alternate_slug":
        base = payload.get("slug") or workflow_key
        alternates = [f"{base}-2026", f"{base}-academy", f"{base}-school"]
        return {
            "ok": True,
            "dry_run": True,
            "would_apply": kind,
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
            "note": "Would mark run running and stamp retry metadata in payload_summary.",
        }

    if kind in ("requeue_provision", "resend_welcome", "retry_dns_sync"):
        return {
            "ok": True,
            "dry_run": True,
            "would_apply": kind,
            "workflow_key": workflow_key,
            "note": "Owner-safe provisioning remediation (idempotent).",
        }

    return {"ok": False, "dry_run": True, "reason": "unsupported_fix_kind", "kind": kind}


def apply_auto_fix_kind(*, run: Any, kind: str) -> dict[str, Any]:
    """Execute a supported ``auto_fix_kind``. Returns JSON-serializable result."""

    from apps.platform_runtime.models import WorkflowRun

    workflow_key = getattr(run, "workflow_key", "")
    payload = dict(getattr(run, "payload_summary", None) or {})

    if kind == "suggest_alternate_slug":
        base = payload.get("slug") or workflow_key
        alternates = [f"{base}-2026", f"{base}-academy", f"{base}-school"]
        return {"ok": True, "applied": kind, "alternates": alternates}

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
        }

    if kind == "requeue_provision" and workflow_key == "tenant_school_provision":
        school_id = str(getattr(run, "school_id", "") or payload.get("school_id") or "")
        if not school_id:
            return {"ok": False, "reason": "missing_school_id", "kind": kind}
        from apps.schools.tasks import dispatch_provision_school

        contact = str(payload.get("contact_email") or "").strip()
        dispatch_provision_school(school_id, contact_email=contact)
        return {"ok": True, "applied": kind, "school_id": school_id}

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
        return {"ok": True, "applied": kind, "school_id": school_id}

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
        return {"ok": True, "applied": kind, "school_id": school_id}

    return {"ok": False, "reason": "unsupported_fix_kind", "kind": kind}
