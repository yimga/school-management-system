"""HTTP auth guards for JSON/SSE/fetch endpoints.

``login_required`` redirects anonymous browsers to the login page (302). That
is correct for HTML navigations but breaks ``EventSource``, ``fetch``, and XHR
clients on public shells — they follow the redirect, download the full login
HTML, and reconnect in a tight loop.

Use ``login_required_api`` (or ``login_required_sse``) on API views and pair
with ``UnauthenticatedApiGuardMiddleware`` so anonymous calls stop with 401
even when a view still uses Django's ``login_required``.
"""

from __future__ import annotations

from functools import wraps

from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponse, JsonResponse


def request_prefers_api_auth_response(request) -> bool:
    """True when the client expects JSON/SSE, not an HTML login redirect."""

    path = (request.path or "").lower()
    accept = (request.META.get("HTTP_ACCEPT") or "").lower()
    if path.endswith(".json"):
        return True
    if "/stream/" in path or path.rstrip("/").endswith("/stream"):
        return True
    if "text/event-stream" in accept:
        return True
    if "application/json" in accept:
        return True
    if request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest":
        return True
    sec_dest = (request.META.get("HTTP_SEC_FETCH_DEST") or "").lower()
    if sec_dest in ("empty", "websocket"):
        return True
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        ctype = (request.META.get("CONTENT_TYPE") or "").lower()
        if "application/json" in ctype:
            return True
    return False


def login_required_api(view_func=None, *, sse: bool = False):
    """Require auth; return 401 for API/SSE clients instead of redirecting.

    Async-aware: when wrapping an ``async def`` view (e.g. an ASGI SSE stream),
    returns an async wrapper so Django runs it on the event loop without a
    sync/async adapter. Sync views keep the original sync wrapper unchanged.
    """

    def _unauthenticated_response(request):
        if sse or request_prefers_api_auth_response(request):
            return HttpResponse(status=401)
        return redirect_to_login(
            request.get_full_path(),
            login_url=settings.LOGIN_URL,
        )

    def decorator(fn):
        if iscoroutinefunction(fn):

            @wraps(fn)
            async def awrapper(request, *args, **kwargs):
                # request.user is a lazy object whose evaluation may hit the DB;
                # resolve it off the event loop to avoid SynchronousOnlyOperation.
                is_authenticated = await sync_to_async(
                    lambda: bool(getattr(request.user, "is_authenticated", False))
                )()
                if is_authenticated:
                    return await fn(request, *args, **kwargs)
                return _unauthenticated_response(request)

            markcoroutinefunction(awrapper)
            return awrapper

        @wraps(fn)
        def wrapper(request, *args, **kwargs):
            if getattr(request.user, "is_authenticated", False):
                return fn(request, *args, **kwargs)
            return _unauthenticated_response(request)

        return wrapper

    if view_func is not None:
        return decorator(view_func)
    return decorator


def login_required_sse(view_func):
    """SSE alias — anonymous clients always receive 401."""

    return login_required_api(view_func, sse=True)


def json_login_required(view_func):
    """JSON endpoints — anonymous clients always receive 401."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if getattr(request.user, "is_authenticated", False):
            return view_func(request, *args, **kwargs)
        return JsonResponse({"error": "authentication_required"}, status=401)

    return wrapper
