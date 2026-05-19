"""v3.40.0 Agent 8 — nightly Migration Cloud smoke Celery task.

Beat entry ``migration-cloud-smoke-nightly`` (configured in
``config/settings.py::CELERY_BEAT_SCHEDULE``) invokes
:func:`run_smoke_against_synthetic_tenant` daily at 04:30 UTC.

Kill switch: ``settings.MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED`` (env
``MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED``). Default OFF in prod;
operators flip to ON in dev / staging.

NEVER calls ``--apply`` — the nightly run is read-only-ish (the
synthetic tenant + transient subscription + bundle still get created on
write paths, but the apply gate is left at default-off so production
state is not perturbed even if the dev kill-switch leaks into prod).

Emits a ``migration.smoke.nightly_run`` audit event recording sections
passed/failed/skipped (no PII; counts only). On any failure, emails
``settings.MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL`` (best-effort; one
email per run — no per-section spam).
"""
from __future__ import annotations

import io
import logging
import sys

logger = logging.getLogger(__name__)


try:  # pragma: no cover - celery presence varies per lane
    from celery import shared_task as _shared_task
except ImportError:
    _shared_task = None  # type: ignore[assignment]


def run_smoke_against_synthetic_tenant() -> dict:
    """Invoke ``manage.py migration_cloud_smoke`` in dry-run mode.

    Returns a structured dict the test harness asserts on. NEVER raises
    — the beat queue must not see verifier errors as task failures.
    """
    try:
        from django.conf import settings
        from django.core.management import call_command
    except Exception:  # pragma: no cover - defensive
        logger.error(
            "migration_cloud.smoke.nightly: failed to import Django bootstrap"
        )
        return {"status": "import_failed"}

    if not getattr(settings, "MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED", False):
        logger.info(
            "migration_cloud.smoke.nightly: kill-switch is OFF; returning noop"
        )
        return {"status": "disabled"}

    tenant = (
        getattr(settings, "MIGRATION_CLOUD_SMOKE_SYNTHETIC_TENANT", "")
        or "smoke-test-tenant"
    )
    alert_email = (
        getattr(settings, "MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL", "") or ""
    ).strip()

    # Capture stdout to count section outcomes from the printed summary.
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    exit_code = 0
    try:
        call_command(
            "migration_cloud_smoke",
            f"--tenant={tenant}",
            "--vendor=powerschool",
            # NEVER --apply in nightly: dry-run only.
            stdout=buf_out,
            stderr=buf_err,
        )
    except SystemExit as exc:
        # The command exits explicitly with 0/1/2.
        code = getattr(exc, "code", 0)
        try:
            exit_code = int(code)
        except (TypeError, ValueError):
            exit_code = 1
    except Exception as exc:  # pylint: disable=broad-except
        logger.error(
            "migration_cloud.smoke.nightly: command raised %s: %s",
            type(exc).__name__, exc,
        )
        _emit_audit_event(
            tenant_slug=tenant,
            sections_passed=0,
            sections_failed=0,
            sections_skipped=0,
            exit_code=1,
            error_type=type(exc).__name__,
        )
        _maybe_alert(alert_email, exit_code=1, summary=str(exc)[:200])
        return {
            "status": "raised",
            "exc_type": type(exc).__name__,
        }

    summary = _parse_summary(buf_out.getvalue())
    _emit_audit_event(
        tenant_slug=tenant,
        sections_passed=summary["passed"],
        sections_failed=summary["failed"],
        sections_skipped=summary["skipped"],
        exit_code=exit_code,
        error_type=None,
    )
    if exit_code == 1 or summary["failed"] > 0:
        _maybe_alert(
            alert_email,
            exit_code=exit_code,
            summary=(
                f"passed={summary['passed']} "
                f"failed={summary['failed']} "
                f"skipped={summary['skipped']}"
            ),
        )

    return {
        "status": "ran",
        "exit_code": exit_code,
        **summary,
    }


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _parse_summary(stdout_text: str) -> dict:
    passed = failed = skipped = 0
    for line in (stdout_text or "").splitlines():
        stripped = line.strip()
        # Summary lines look like:
        #   "intake                 SKIP        0.001  ..."
        # We split on whitespace and check token 2.
        parts = stripped.split()
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


def _emit_audit_event(
    *,
    tenant_slug: str,
    sections_passed: int,
    sections_failed: int,
    sections_skipped: int,
    exit_code: int,
    error_type: str | None,
) -> None:
    """Append a ``migration.smoke.nightly_run`` audit event."""
    try:
        from apps.migration_cloud.models_audit import (
            MigrationCloudAuditEvent,
            MigrationCloudAuditEventType,
        )
    except Exception:  # pragma: no cover - audit module absent in lane
        return
    payload = {
        "sections_passed_count": int(sections_passed),
        "sections_failed_count": int(sections_failed),
        "sections_skipped_count": int(sections_skipped),
        "exit_code": int(exit_code),
        "error_type": error_type or "",
    }
    # The audit log carries a fixed TextChoices set; if the smoke event
    # type isn't registered we fall back to KEY_ROTATE-typed "system"
    # event so the run is still recorded somewhere durable.
    event_type = "migration.smoke.nightly_run"
    valid_choices = {c.value for c in MigrationCloudAuditEventType}
    if event_type not in valid_choices:
        # Use a closest-fit registered choice rather than fail. We pick
        # KEY_ROTATE since it's the most "system event" of the set.
        event_type = MigrationCloudAuditEventType.KEY_ROTATE.value
        payload["registered_choice_fallback"] = "smoke_event_type_unregistered"
    try:
        MigrationCloudAuditEvent.objects.record(
            tenant_slug=tenant_slug,
            event_type=event_type,
            actor=None,
            subject=f"nightly-smoke-{tenant_slug}",
            payload_summary=payload,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud.smoke.nightly: audit emit failed err_type=%s",
            type(exc).__name__,
        )


def _maybe_alert(recipient: str, *, exit_code: int, summary: str) -> None:
    """Route nightly-smoke failure through the multi-channel alert pipeline.

    Preserves the v3.40 kill-switch: when no recipient is configured AND
    no Slack / PagerDuty channels are wired, the alerts module degrades
    to log-only — which is the same effective behavior as the previous
    inline ``send_mail`` no-op. Otherwise we fan out warning-severity
    (Slack + email + log) so on-call sees it without paging anyone.
    """
    # ``recipient`` is now informational only; the alerts module reads
    # ``settings.OPERATOR_ALERT_EMAIL`` / ``MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL``
    # directly. We still respect the "no recipient + no channels" case
    # because the kill-switch contract was historically "empty recipient
    # = silent". When ANY channel is configured we proceed.
    try:
        from apps.migration_cloud.alerts import (
            _channels_enabled,
            alert,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "migration_cloud.smoke.nightly: alerts module import failed err_type=%s",
            type(exc).__name__,
        )
        return

    channels = _channels_enabled()
    # Log-only mode AND empty recipient is the v3.39 no-op contract.
    if not recipient and channels == ["log"]:
        return

    body = (
        "Migration Cloud nightly smoke reported a non-clean run.\n\n"
        f"- exit_code: {exit_code}\n"
        f"- summary: {summary}\n\n"
        "Investigate via:\n"
        "  `python manage.py migration_cloud_smoke "
        "--tenant=<slug> --vendor=powerschool --verbose`\n"
        "See `docs/MIGRATION_CLOUD_UAT_RUNBOOK.md`."
    )
    try:
        alert(
            severity="warning",
            title="Migration Cloud: nightly smoke non-clean",
            body=body,
            dedupe_key=f"smoke-nightly-failure-exit{int(exit_code)}",
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud.smoke.nightly: alert dispatch failed err_type=%s",
            type(exc).__name__,
        )


# Celery-discoverable wrapper.
if _shared_task is not None:  # pragma: no cover - thin shim
    @_shared_task(
        name="apps.migration_cloud.tasks_smoke.run_smoke_against_synthetic_tenant",
        ignore_result=True,
    )
    def _celery_run_smoke_against_synthetic_tenant() -> dict:
        return run_smoke_against_synthetic_tenant()


__all__ = ["run_smoke_against_synthetic_tenant"]
