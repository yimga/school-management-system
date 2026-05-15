"""Wave C — G2: DB-session metering middleware.

Increments the ``db_sessions`` dimension once per unique
``(school, browser-session, utc_day)`` triple. The cookie-derived session
key is the natural unit of "one user using the platform today" — the
same definition AWS uses for billable Lambda/concurrent-user counts.

Never raises into the request path; telemetry must not break navigation.
"""

from __future__ import annotations

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


SESSION_COUNTED_KEY = "rmc_db_session_counted_day"


class DBSessionMeteringMiddleware:
    """Count the first authenticated request of each browser session per day."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._record(request)
        except Exception as exc:  # noqa: BLE001
            # Defensive: never propagate from telemetry. We accept bare-ish
            # except here because this runs on every authenticated request
            # path and a typed list would simply be `Exception` anyway.
            logger.debug("db_session_metering swallow: %s", exc)
        return response

    def _record(self, request) -> None:
        user = getattr(request, "user", None)
        school = getattr(request, "school", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return
        if school is None:
            return
        session = getattr(request, "session", None)
        if session is None:
            return

        today_iso = timezone.now().date().isoformat()
        if session.get(SESSION_COUNTED_KEY) == today_iso:
            return  # already counted this session+day

        from apps.billing.models_metering import record

        record(school, "db_sessions", delta=1)
        session[SESSION_COUNTED_KEY] = today_iso
