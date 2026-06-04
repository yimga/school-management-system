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

    return {"ok": False, "reason": "unsupported_fix_kind", "kind": kind}
