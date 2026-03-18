import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class PlatformRuntimeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform_runtime"
    verbose_name = "Platform runtime (defaults, resolver)"

    def ready(self) -> None:
        try:
            from apps.platform_runtime.celery_task_events import (
                connect_celery_platform_task_signals,
            )

            connect_celery_platform_task_signals()
        except Exception:
            logger.debug(
                "Celery platform task signals not connected at Django ready",
                exc_info=True,
            )
