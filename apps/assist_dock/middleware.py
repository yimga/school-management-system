"""v4.00.96 Wave F3 — per-user locale persistence middleware.

When a user has set ``locale_preference`` in their UserAssistDockPrefs
payload, this middleware overrides Django's resolved language for the
request. Runs AFTER ``django.middleware.locale.LocaleMiddleware`` so it
sees the locale Django picked + can replace it. Anonymous / unset
preference → no-op (LocaleMiddleware's pick stands).

Defensive: any failure logs at DEBUG and lets the request continue with
Django's original locale. Never raises.
"""

from __future__ import annotations

import logging

from django.utils import translation

logger = logging.getLogger(__name__)


class AssistDockLocaleMiddleware:
    """Override LANGUAGE_CODE from UserAssistDockPrefs when present."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            preferred = self._resolve_preferred_locale(request)
        except Exception as exc:  # noqa: BLE001 — middleware must never raise
            logger.debug("assist_dock locale middleware lookup failed: %s", exc)
            preferred = ""
        if preferred:
            try:
                translation.activate(preferred)
                request.LANGUAGE_CODE = preferred
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "assist_dock locale activate %r failed: %s", preferred, exc
                )
        return self.get_response(request)

    def _resolve_preferred_locale(self, request) -> str:
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return ""
        try:
            from .models import get_or_default_prefs
        except (ImportError, RuntimeError):
            return ""
        payload = get_or_default_prefs(user)
        if not isinstance(payload, dict):
            return ""
        candidate = str(payload.get("locale_preference") or "").strip()
        if not candidate:
            return ""
        # Only honor a code we recognise via Django settings.LANGUAGES so a
        # malformed pref never breaks every page.
        try:
            from django.conf import settings

            recognised = {code.lower() for code, _ in getattr(settings, "LANGUAGES", [])}
        except (AttributeError, RuntimeError):
            recognised = set()
        if recognised and candidate.lower() not in recognised:
            return ""
        return candidate
