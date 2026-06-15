"""Return 401 (not 302) for anonymous API traffic on operator realtime paths."""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpResponse

logger = logging.getLogger(__name__)

_WORKFLOW_PREFIX = "/platform-runtime/workflow-progress/"
_ASSIST_DOCK_PREFIX = "/assist-dock/"
_WAL_WS_PREFIX = "/ws/wal/"
# HTML landings — allow normal login redirect for direct navigation.
_ASSIST_DOCK_HTML_SUFFIXES = frozenset(
    {
        "translate",
        "share",
        "theme",
        "inspect",
        "impersonate",
        "presence",
        "settings",
        "impersonation",
    }
)


def _assist_dock_requires_api_auth(path: str, method: str) -> bool:
    if not path.startswith(_ASSIST_DOCK_PREFIX):
        return False
    # Public share-link resolver (24h token).
    if path.startswith(f"{_ASSIST_DOCK_PREFIX}s/"):
        return False
    if method == "GET":
        trimmed = path.rstrip("/")
        tail = trimmed.rsplit("/", 1)[-1] if trimmed else ""
        if tail in _ASSIST_DOCK_HTML_SUFFIXES and not path.endswith(".json"):
            return False
    return True


def path_requires_unauthenticated_api_auth(path: str, method: str) -> bool:
    """Public helper — manager middleware uses this before HTML login redirects."""

    if path.startswith(_WORKFLOW_PREFIX):
        return True
    if path.startswith(_WAL_WS_PREFIX) or path.rstrip("/") == _WAL_WS_PREFIX.rstrip("/"):
        return True
    return _assist_dock_requires_api_auth(path, method)


class UnauthenticatedApiGuardMiddleware:
    """Short-circuit anonymous realtime/API calls before view-level 302 redirects."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return self.get_response(request)
        path = request.path or ""
        if path_requires_unauthenticated_api_auth(path, request.method):
            # Observe-only diagnostic (off by default; set RMC_DEBUG_API_AUTH_401=1
            # to enable). Logs ONLY booleans/presence — never cookie values or
            # tokens — so we can tell WHY the request is anonymous here without
            # touching any auth logic:
            #   has_default_cookie True + user_authed False  -> session cookie
            #       present but didn't resolve to a user (alias / session-load issue)
            #   has_default_cookie False + has_manager_cookie True -> the manager
            #       cookie alias didn't apply for this request
            #   both False -> the browser sent no session cookie (credentials /
            #       SameSite / cross-origin), not a server-side aliasing bug
            if getattr(settings, "RMC_DEBUG_API_AUTH_401", False):
                cookies = getattr(request, "COOKIES", {}) or {}
                default_name = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
                sess = getattr(request, "session", None)
                logger.warning(
                    "unauthenticated_api_guard_401 path=%s method=%s user_present=%s "
                    "user_authed=%s has_default_cookie=%s has_manager_cookie=%s "
                    "session_key_resolved=%s",
                    path,
                    request.method,
                    user is not None,
                    bool(user is not None and getattr(user, "is_authenticated", False)),
                    default_name in cookies,
                    "rmc_manager_sessionid" in cookies,
                    bool(sess is not None and getattr(sess, "session_key", None)),
                )
            return HttpResponse(status=401)
        return self.get_response(request)
