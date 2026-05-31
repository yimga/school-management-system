"""Return 401 (not 302) for anonymous API traffic on operator realtime paths."""

from __future__ import annotations

from django.http import HttpResponse

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


def _path_requires_api_auth(path: str, method: str) -> bool:
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
        if _path_requires_api_auth(path, request.method):
            return HttpResponse(status=401)
        return self.get_response(request)
