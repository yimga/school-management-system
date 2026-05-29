"""Portal app configuration — startup checks for live AI posture."""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class PortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.portal"
    verbose_name = "Portal"

    def ready(self) -> None:
        from apps.portal.ai_startup import management_command_skips_ai_startup_probe

        if management_command_skips_ai_startup_probe():
            return
        try:
            from django.conf import settings

            if not getattr(settings, "AI_GATEWAY_ENABLED", True):
                return
            from apps.portal.ai_provider import (
                log_ai_startup_posture,
                probe_ai_provider_reachable,
                resolve_ollama_connection,
            )

            health = probe_ai_provider_reachable()
            conn: dict = {}
            provider = str(health.get("provider") or "").lower()
            if provider == "ollama" or not health.get("reachable"):
                conn = resolve_ollama_connection(force_refresh=True)
            log_ai_startup_posture(health=health, conn=conn)
        except Exception:  # noqa: BLE001 — never block Django boot on AI probe
            logger.debug("AI startup probe skipped", exc_info=True)

        # v4.00.36 — register live-checks for the canonical wedge registry.
        # Import is the registration trigger; module is side-effecting on purpose.
        try:
            from apps.portal import wedge_checks  # noqa: F401
        except Exception:  # noqa: BLE001 — never block boot on wedge plumbing
            logger.debug("wedge check registration skipped", exc_info=True)
