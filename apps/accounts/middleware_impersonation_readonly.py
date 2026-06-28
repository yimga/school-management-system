"""Read-only operator-impersonation enforcement (Wave C #4 Phase 3a).

When a platform operator impersonates a tenant with ``read_only=True``, the session
captures that intent (``request.session["impersonation"]["read_only"]``) but historically
nothing BLOCKED writes — it was logged, never enforced. This middleware rejects unsafe
HTTP methods (POST/PUT/PATCH/DELETE) during a read-only impersonation session with 403,
except an allowlist of URL names the operator needs to leave the session.

**Feature-flagged, default OFF.** It is a complete no-op unless
``settings.IMPERSONATION_READ_ONLY_ENFORCED`` is truthy, so it is safe to wire into
MIDDLEWARE and switch on only after request-path (Playwright) verification — a misjudged
allowlist would otherwise block a legitimate operator support action.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# URL names the operator must still reach to exit a read-only session, even while
# writes are otherwise blocked.
_ALLOW_URL_NAMES = frozenset(
    {
        "end_impersonation",
        "impersonation_stop",
        "impersonation_stop_redirect",
        "logout",
        "account_logout",
    }
)


def _is_read_only_impersonation(request) -> bool:
    """True iff the current request is an impersonation session marked read-only."""
    try:
        session = getattr(request, "session", None)
        imp = session.get("impersonation") if session is not None else None
    except Exception:  # noqa: BLE001 — a session read must never break the request
        return False
    return bool(isinstance(imp, dict) and imp.get("read_only"))


class ReadOnlyImpersonationGuardMiddleware(MiddlewareMixin):
    """Reject writes during a read-only impersonation session (feature-flagged)."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not getattr(settings, "IMPERSONATION_READ_ONLY_ENFORCED", False):
            return None
        if request.method not in _UNSAFE_METHODS:
            return None
        if not _is_read_only_impersonation(request):
            return None
        match = getattr(request, "resolver_match", None)
        url_name = getattr(match, "url_name", None) if match else None
        if url_name in _ALLOW_URL_NAMES:
            return None
        logger.warning(
            "impersonation.read_only.write_blocked path=%s method=%s url_name=%s",
            getattr(request, "path", "?"),
            request.method,
            url_name,
        )
        return HttpResponseForbidden(
            "This is a read-only support session. Writes are disabled."
        )
