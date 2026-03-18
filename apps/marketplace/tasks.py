"""
Celery tasks for marketplace (health checks, etc.).
Schedule in CELERY_BEAT_SCHEDULE or run: marketplace_health_check.delay()
§2.4: Typed exception tuple for record_installation_health loop (no broad except).
"""

import logging
from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, IntegrityError

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
