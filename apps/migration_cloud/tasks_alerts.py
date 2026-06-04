"""v3.40.0 Agent 12 — alert-source Celery tasks.

Currently houses one beat task:

  * :func:`token_rotation_watchdog` — finds Migration Cloud API tokens
    whose ``grace_until`` has elapsed and which were never rotated
    (``rotated_to__isnull=True``), then emits one ``warning`` alert per
    overdue token via :func:`apps.migration_cloud.alerts.alert`.

The alerts module's per-hour rate limit caps fan-out so a stale
hundreds-of-tokens backlog won't spam PagerDuty (warning severity
doesn't page anyway, but Slack would still complain).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


try:  # pragma: no cover - celery presence varies per lane
    from celery import shared_task as _shared_task
except ImportError:
    _shared_task = None  # type: ignore[assignment]


def token_rotation_watchdog() -> dict:
    """Emit a warning alert per overdue-rotation API token.

    Overdue = ``grace_until < now()`` AND ``rotated_to__isnull=True``
    AND ``revoked_at IS NOT NULL`` (the operator marked the old token
    revoked, started the rollout window, then forgot to update clients).
    NEVER raises.
    """
    try:
        from django.utils import timezone
        from apps.migration_cloud.alerts import alert
        from apps.migration_cloud.models import MigrationCloudAPIToken
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "migration_cloud.token_watchdog: import failed err_type=%s",
            type(exc).__name__,
        )
        return {"status": "import_failed"}

    now = timezone.now()
    # tenant-isolation: this queryset deliberately spans tenants because
    # the watchdog is an operator-side concern, and the token model is
    # scoped via FK (``tenant_scope``) rather than schema. We do not
    # leak tenant data — only the token id + tenant_scope_id appears in
    # the alert dedup_key.
    qs = (
        MigrationCloudAPIToken.objects
        .filter(grace_until__lt=now, rotated_to__isnull=True)
        # tenant-isolation-marker: cross-tenant operator scan, intentional
        .exclude(grace_until__isnull=True)
        .only("id", "name", "tenant_scope_id", "grace_until")
    )

    emitted = 0
    scanned = 0
    try:
        for tok in qs.iterator():
            scanned += 1
            dedupe_key = f"token-overdue-{tok.pk}"
            tenant_part = (
                f"tenant_scope_id={tok.tenant_scope_id}"
                if tok.tenant_scope_id is not None
                else "tenant_scope_id=none"
            )
            try:
                alert(
                    severity="warning",
                    title="Migration Cloud: token rotation overdue",
                    body=(
                        "An API token's grace_until has elapsed but no "
                        "successor was set. Clients still authenticating "
                        "with the old token will start failing at the next "
                        "auth refresh.\n\n"
                        f"- token_id: {tok.pk}\n"
                        f"- {tenant_part}\n"
                        f"- grace_until: {tok.grace_until.isoformat() if tok.grace_until else 'unset'}\n"
                        "\nRun `python manage.py shell` and call "
                        "`MigrationCloudAPIToken.objects.get(pk=...).rotate()` "  # tenant-isolation-allow: celery-migration-cloud-token-admin-by-pk
                        "or revoke + re-issue."
                    ),
                    dedupe_key=dedupe_key,
                    links=None,
                )
                emitted += 1
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "migration_cloud.token_watchdog: alert raised err_type=%s tok_id=%s",
                    type(exc).__name__, tok.pk,
                )
    except Exception as exc:  # pylint: disable=broad-except
        logger.error(
            "migration_cloud.token_watchdog: queryset iteration failed err_type=%s",
            type(exc).__name__,
        )
        return {"status": "queryset_failed", "scanned": scanned, "emitted": emitted}

    logger.info(
        "migration_cloud_token_watchdog scanned=%s emitted=%s",
        scanned, emitted,
    )
    return {"status": "ran", "scanned": scanned, "emitted": emitted}


if _shared_task is not None:  # pragma: no cover - thin shim
    @_shared_task(
        name="apps.migration_cloud.tasks_alerts.token_rotation_watchdog",
        ignore_result=True,
    )
    def _celery_token_rotation_watchdog() -> dict:
        return token_rotation_watchdog()


__all__ = ["token_rotation_watchdog"]
