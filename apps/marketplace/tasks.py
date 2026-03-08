"""
Celery tasks for marketplace (health checks, etc.).
Schedule in CELERY_BEAT_SCHEDULE or run: marketplace_health_check.delay()
"""
import logging
from celery import shared_task
from django.utils import timezone

from apps.marketplace.models import AppInstallation
from apps.marketplace.services import record_installation_health

logger = logging.getLogger(__name__)


@shared_task(name="marketplace.marketplace_health_check")
def marketplace_health_check(status: str = "ok"):
    """
    Update health for all active app installations. Run periodically via beat.
    """
    qs = AppInstallation.objects.filter(
        status=AppInstallation.Status.ACTIVE,
        uninstalled_at__isnull=True,
    )
    updated = 0
    for inst in qs:
        try:
            record_installation_health(inst, status=status)
            updated += 1
        except Exception as e:
            logger.warning("marketplace_health_check failed for installation %s: %s", inst.pk, e)
    logger.info("marketplace_health_check updated %s installations", updated)
    return updated
