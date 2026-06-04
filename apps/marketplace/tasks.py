"""
Celery tasks for marketplace (health checks, etc.).
Schedule in CELERY_BEAT_SCHEDULE or run: marketplace_health_check.delay()
§2.4: Typed exception tuple for record_installation_health loop (no broad except).
"""

import logging
from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, IntegrityError

from apps.platform_runtime.workflow_tracker import track_workflow, workflow_step

from apps.marketplace.models import AppInstallation
from apps.marketplace.services import record_installation_health
from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

_MARKETPLACE_HEALTH_CHECK_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    ObjectDoesNotExist,
    DatabaseError,
    IntegrityError,
)


@shared_task(name="marketplace.marketplace_health_check")
def marketplace_health_check(status: str = "ok"):
    """
    Update health for all active app installations. Run periodically via beat.
    """
    # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
    qs = AppInstallation.objects.filter(
        status=AppInstallation.Status.ACTIVE,
        uninstalled_at__isnull=True,
    )
    updated = 0
    for inst in qs:
        try:
            record_installation_health(inst, status=status)
            updated += 1
        except _MARKETPLACE_HEALTH_CHECK_ERRORS:
            log_exception_with_context(
                "marketplace_health_check: record_installation_health failed",
                school_id=getattr(inst, "school_id", None),
                extra={"installation_id": inst.pk},
            )
    logger.info("marketplace_health_check updated %s installations", updated)
    return updated


@shared_task(name="marketplace.deliver_install_hooks")
def deliver_install_hooks_task(
    installation_id: str,
    phase: str,
    hook_urls: list[str],
) -> int:
    """POST install/upgrade hook URLs; failures logged, never raised."""
    from apps.marketplace.models import AppInstallation
    from apps.marketplace.install_hook_delivery import deliver_install_hooks_inline

    try:
        inst = AppInstallation.objects.select_related("app", "school").get(
            pk=installation_id
        )
    except AppInstallation.DoesNotExist:
        return 0
    deliver_install_hooks_inline(inst, inst.app, phase, hook_urls)
    return len(hook_urls)


@shared_task(name="marketplace.webhook_deliver_due", bind=True)
@track_workflow(
    "marketplace_webhook_deliver_due",
    steps=("scan", "deliver", "finalize"),
    expected_duration_seconds=120,
)
def webhook_deliver_due(self, limit: int = 50) -> int:
    """Move 1 — drain due WebhookDelivery rows with exponential-backoff retry."""

    try:
        from apps.marketplace.webhooks import deliver_due

        with workflow_step(None, "scan", payload={"limit": int(limit)}):
            pass
        with workflow_step(None, "deliver"):
            delivered = deliver_due(limit=int(limit))
        with workflow_step(None, "finalize", payload={"delivered": int(delivered)}):
            pass
        return int(delivered)
    except Exception as exc:
        logging.getLogger(__name__).warning("webhook_deliver_due failed: %s", exc)
        return 0


webhook_deliver_due.rmc_workflow_explicit = True
