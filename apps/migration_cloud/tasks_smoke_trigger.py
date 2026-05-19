"""v3.40.0 Agent 14 — Celery task backing the "Run Smoke Now" view.

Invoked by ``SmokeRunTriggerView.post()`` (see
``apps/migration_cloud/views_smoke_trigger.py``). Runs the existing
``migration_cloud_smoke`` management command in-process via
``django.core.management.call_command`` (NOT subprocess — the smoke
command is documented safe-to-call-in-process), captures its output,
parses the summary table, and:

  * Audit-emits ``migration.smoke.on_demand_completed`` with section
    counts (PII-free).
  * Best-effort archives the run via Agent 13's
    ``archive_smoke_run`` task (defensive import — race tolerant).
  * Best-effort fires an Agent 12 operator alert
    (``apps.migration_cloud.alerts.alert`` — defensive import).
  * On exception, emits ``migration.smoke.on_demand_failed`` carrying
    only the exception CLASS NAME (never traceback — could leak
    file paths / secrets).

NEVER logs: tenant slug raw form (sha256[:12] prefix only), vendor's
contents beyond the choice name, exception traceback text.
"""
from __future__ import annotations

import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


try:  # pragma: no cover - celery presence varies per lane
    from celery import shared_task as _shared_task
except ImportError:
    _shared_task = None  # type: ignore[assignment]


def _hash_slug_prefix(slug: str) -> str:
    return hashlib.sha256((slug or "").encode("utf-8")).hexdigest()[:12]


def _parse_summary(stdout_text: str) -> dict[str, int]:
    """Mirror Agent 8's tasks_smoke._parse_summary token-scan logic."""
    passed = failed = skipped = 0
    for line in (stdout_text or "").splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        status = parts[1].upper()
        if status == "PASS":
            passed += 1
        elif status == "FAIL":
            failed += 1
        elif status == "SKIP":
            skipped += 1
    return {"passed": passed, "failed": failed, "skipped": skipped}


def _emit_audit(
    *,
    event_type: str,
    tenant_slug: str,
    payload: dict[str, Any],
    requested_by_user_id: int | None,
) -> None:
    """Best-effort audit emit. Rate-limit + lane errors swallowed."""
    try:
        from apps.migration_cloud.models_audit import (
            AuditEventRateLimitExceeded,
            MigrationCloudAuditEvent,
            MigrationCloudAuditEventType,
        )
    except Exception:  # pragma: no cover - audit module absent
        return
    valid = {c.value for c in MigrationCloudAuditEventType}
    if event_type not in valid:
        event_type = MigrationCloudAuditEventType.KEY_ROTATE.value
        payload = {
            **payload,
            "registered_choice_fallback": "smoke_event_type_unregistered",
        }
    actor_email = None
    if requested_by_user_id:
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.filter(pk=requested_by_user_id).only(  # tenant-isolation-allow: smoke-trigger-actor-lookup-by-pk
                "email"
            ).first()
            if user is not None:
                actor_email = getattr(user, "email", None) or None
        except Exception:  # pragma: no cover - defensive
            actor_email = None
    try:
        MigrationCloudAuditEvent.objects.record(
            tenant_slug=tenant_slug,
            event_type=event_type,
            actor=actor_email,
            subject=f"smoke-on-demand-{_hash_slug_prefix(tenant_slug)}",
            payload_summary=payload,
        )
    except AuditEventRateLimitExceeded:
        logger.info(
            "migration_cloud.smoke.on_demand.audit_rate_limited "
            "tenant_hash=%s event_type=%s",
            _hash_slug_prefix(tenant_slug), event_type,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud.smoke.on_demand.audit_emit_failed "
            "tenant_hash=%s err_type=%s",
            _hash_slug_prefix(tenant_slug), type(exc).__name__,
        )


def _maybe_archive(
    *,
    tenant: str,
    vendor: str,
    apply: bool,
    exit_code: int,
    summary: dict[str, int],
    stdout_text: str,
) -> None:
    """Best-effort hand-off to Agent 13's ``archive_smoke_run`` writer.

    Agent 13's signature is ``archive_smoke_run(summary_dict)`` — a
    single dict that gets envelope-wrapped + persisted under
    ``var/smoke-results/<stamp>.json``. We pass a structurally-
    compatible dict matching the nightly task's return shape, plus
    extra ``trigger`` / ``tenant_hash`` / ``vendor`` keys.

    Defensive across multiple plausible module names — race tolerant
    if Agent 13 lands in a different file in a future wave.
    """
    summary_dict = {
        "status": "ran",
        "trigger": "on_demand",
        "tenant_hash": _hash_slug_prefix(tenant),
        "vendor": vendor,
        "apply": bool(apply),
        "exit_code": int(exit_code),
        "passed": int(summary["passed"]),
        "failed": int(summary["failed"]),
        "skipped": int(summary["skipped"]),
        "run_at_iso": datetime.now(timezone.utc).isoformat(),
    }
    for modname, taskname in (
        ("apps.migration_cloud.tasks_smoke_archival", "archive_smoke_run"),
        ("apps.migration_cloud.tasks_smoke_history", "archive_smoke_run"),
        ("apps.migration_cloud.tasks_smoke_archive", "archive_smoke_run"),
    ):
        try:
            module = __import__(modname, fromlist=[taskname])
        except Exception:
            continue
        task = getattr(module, taskname, None)
        if task is None:
            continue
        try:
            if hasattr(task, "delay"):
                task.delay(summary_dict)
            else:
                task(summary_dict)
            return
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "migration_cloud.smoke.on_demand.archive_failed "
                "tenant_hash=%s err_type=%s",
                _hash_slug_prefix(tenant), type(exc).__name__,
            )
            return
    return


def _maybe_alert(
    *,
    tenant: str,
    vendor: str,
    exit_code: int,
    summary: dict[str, int],
) -> None:
    """Best-effort hand-off to Agent 12's alert() function."""
    try:
        from apps.migration_cloud.alerts import alert  # type: ignore
    except ImportError:
        return
    except Exception:  # pragma: no cover - defensive
        return
    severity = "info" if exit_code == 0 else "warning"
    title = (
        f"Smoke {tenant}/{vendor} "
        f"{'OK' if exit_code == 0 else 'FAILED'}"
    )
    body = (
        f"on-demand smoke completed exit_code={exit_code} "
        f"passed={summary['passed']} "
        f"failed={summary['failed']} "
        f"skipped={summary['skipped']}"
    )
    try:
        alert(  # type: ignore[misc]
            severity=severity,
            title=title,
            body=body,
            tags={"source": "smoke_on_demand", "vendor": vendor},
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud.smoke.on_demand.alert_failed "
            "tenant_hash=%s err_type=%s",
            _hash_slug_prefix(tenant), type(exc).__name__,
        )


def _run_smoke_on_demand_impl(
    tenant: str,
    vendor: str,
    apply: bool,
    requested_by_user_id: int | None,
) -> dict[str, Any]:
    """Plain-Python core. Exposed via @shared_task wrapper below."""
    try:
        from django.core.management import call_command
    except Exception:  # pragma: no cover - defensive
        return {"status": "django_unavailable"}

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    exit_code = 0
    args: list[str] = [
        f"--tenant={tenant}",
        f"--vendor={vendor}",
    ]
    if apply:
        args.append("--apply")
    try:
        call_command(
            "migration_cloud_smoke",
            *args,
            stdout=buf_out,
            stderr=buf_err,
        )
    except SystemExit as sx:
        code = getattr(sx, "code", 0)
        try:
            exit_code = int(code) if code is not None else 0
        except (TypeError, ValueError):
            exit_code = 1
    except Exception as exc:  # pylint: disable=broad-except
        # Audit a failed run — NEVER the traceback, just the class name.
        _emit_audit(
            event_type="migration.smoke.on_demand_failed",
            tenant_slug=tenant,
            payload={
                "vendor": vendor,
                "apply": bool(apply),
                "exception_class": type(exc).__name__,
            },
            requested_by_user_id=requested_by_user_id,
        )
        logger.warning(
            "migration_cloud.smoke.on_demand.command_raised "
            "tenant_hash=%s err_type=%s",
            _hash_slug_prefix(tenant), type(exc).__name__,
        )
        return {
            "status": "raised",
            "exception_class": type(exc).__name__,
        }

    stdout_text = buf_out.getvalue()
    summary = _parse_summary(stdout_text)

    _emit_audit(
        event_type="migration.smoke.on_demand_completed",
        tenant_slug=tenant,
        payload={
            "vendor": vendor,
            "apply": bool(apply),
            "exit_code": int(exit_code),
            "sections_passed": int(summary["passed"]),
            "sections_failed": int(summary["failed"]),
            "sections_skipped": int(summary["skipped"]),
        },
        requested_by_user_id=requested_by_user_id,
    )
    _maybe_archive(
        tenant=tenant,
        vendor=vendor,
        apply=apply,
        exit_code=exit_code,
        summary=summary,
        stdout_text=stdout_text,
    )
    _maybe_alert(
        tenant=tenant, vendor=vendor, exit_code=exit_code, summary=summary,
    )
    return {
        "status": "ran",
        "exit_code": exit_code,
        **summary,
    }


# Public API: the view calls ``run_smoke_on_demand`` directly, expecting
# either ``.delay(...)`` (when celery is wired) or a synchronous call
# fallback. We give it both.
if _shared_task is not None:  # pragma: no cover - thin celery shim
    @_shared_task(
        name="apps.migration_cloud.tasks_smoke_trigger.run_smoke_on_demand",
        ignore_result=True,
    )
    def run_smoke_on_demand(
        tenant: str,
        vendor: str,
        apply: bool,
        requested_by_user_id: int | None = None,
    ) -> dict[str, Any]:
        return _run_smoke_on_demand_impl(
            tenant, vendor, apply, requested_by_user_id,
        )
else:
    def run_smoke_on_demand(  # type: ignore[no-redef]
        tenant: str,
        vendor: str,
        apply: bool,
        requested_by_user_id: int | None = None,
    ) -> dict[str, Any]:
        return _run_smoke_on_demand_impl(
            tenant, vendor, apply, requested_by_user_id,
        )


__all__ = ["run_smoke_on_demand", "_run_smoke_on_demand_impl"]
