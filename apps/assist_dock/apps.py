"""v4.00.91 — assist dock AppConfig."""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AssistDockConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assist_dock"
    label = "assist_dock"
    verbose_name = "Assist Dock"

    def ready(self) -> None:  # pragma: no cover - imports at app load
        # Seed the registry with the 6 legacy DOM-adopted chips so the
        # context processor surfaces them on day 1 without touching any
        # other app's templates. Other apps add chips by calling
        # ``apps.assist_dock.registry.register_slot(...)`` from their own
        # AppConfig.ready hook — no central registration required.
        try:
            from . import default_slots  # noqa: F401
        except (ImportError, RuntimeError) as exc:
            logger.debug("assist_dock default slots load skipped: %s", exc)
        # Wave B: pluggable badge resolvers — register the 6 v1 defaults.
        try:
            from . import default_badges  # noqa: F401
        except (ImportError, RuntimeError) as exc:
            logger.debug("assist_dock default badges load skipped: %s", exc)
        # Wave C: 6 power chips (translate, share, theme, voice, inspect, impersonate).
        try:
            from . import power_chips  # noqa: F401
        except (ImportError, RuntimeError) as exc:
            logger.debug("assist_dock power chips load skipped: %s", exc)
        # Wave D: built-in AI actions (summarize / explain / draft / translate).
        try:
            from . import default_ai_actions  # noqa: F401
        except (ImportError, RuntimeError) as exc:
            logger.debug("assist_dock default AI actions load skipped: %s", exc)
