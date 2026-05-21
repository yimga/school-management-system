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
        # Skip during migrations / collectstatic / most management commands.
        import sys

        if any(
            cmd in sys.argv
            for cmd in (
                "migrate",
                "makemigrations",
                "collectstatic",
                "shell",
                "test",
                "pytest",
            )
        ):
            return
        try:
            from django.conf import settings

            if not getattr(settings, "AI_GATEWAY_ENABLED", True):
                return
            from apps.portal.ai_provider import (
                ai_rules_fallback_allowed,
                ollama_require_live,
                probe_ai_provider_reachable,
                resolve_ollama_connection,
            )

            conn = resolve_ollama_connection(force_refresh=True)
            health = probe_ai_provider_reachable()
            if health.get("reachable"):
                logger.info(
                    "AI startup: live Ollama at %s (discovery=%s)",
                    conn.get("base_url"),
                    conn.get("discovery_source"),
                )
            elif ollama_require_live():
                logger.error(
                    "AI startup: OLLAMA_REQUIRE_LIVE=1 but Ollama is not reachable at %s. "
                    "Assistants will return 'live AI unavailable' (not template fallback). "
                    "Run: python scripts/verify_ollama_live.py --strict --invoke",
                    conn.get("base_url"),
                )
            elif ai_rules_fallback_allowed():
                logger.warning(
                    "AI startup: Ollama not reachable; intelligent grounded fallback is active."
                )
        except Exception:  # noqa: BLE001 — never block Django boot on AI probe
            logger.debug("AI startup probe skipped", exc_info=True)
