import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class PlatformRuntimeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform_runtime"
    verbose_name = "Platform runtime (defaults, resolver)"

    def ready(self) -> None:
        try:
            from apps.platform_runtime import fleet_signals  # noqa: F401 — register receivers

        except Exception:
            logger.debug(
                "Fleet governed change signals not connected at Django ready",
                exc_info=True,
            )
        try:
            from apps.platform_runtime.platform_loop_attendance import (
                register_platform_loop_attendance_subscriber,
            )

            register_platform_loop_attendance_subscriber()
        except Exception:
            logger.debug(
                "Platform loop attendance_saved subscriber not registered",
                exc_info=True,
            )
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
        try:
            from apps.platform_runtime.platform_event_bridge import (
                register_platform_event_ai_bridge,
                register_platform_event_analytics_bridge,
            )

            register_platform_event_ai_bridge()
            register_platform_event_analytics_bridge()
        except Exception:
            logger.debug(
                "Platform event AI/analytics bridge not registered at Django ready",
                exc_info=True,
            )
