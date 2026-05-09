"""Per-endpoint sliding-window rate limiter, cache-backed.

Designed to be used as a Django decorator on sensitive endpoints (login,
password reset, partner OAuth token mint, contact form, etc.). Implements a
fixed-window counter against the configured Django cache; thread-safe via the
cache backend's atomic ``add`` + ``incr``. No new dependency.

Default behavior:
- Key = ``"rl:{scope}:{client_id}:{window_start}"`` where window_start is
  the integer unix-second floor-divided by ``window_seconds``.
- Client_id default = remote_addr; can be overridden via ``key`` callable.
- Exceeding the limit returns HTTP 429 with a ``Retry-After`` header.

Example::

    from apps.security.rate_limit import rate_limit

    @rate_limit(scope="login", limit=10, window_seconds=60)
    def login_view(request):
        ...

The middleware is OFF when ``settings.RATE_LIMIT_ENABLED`` is False.
"""

from __future__ import annotations

import time
from functools import wraps
from typing import Callable

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


def _client_id_from_request(request) -> str:
    """Best-effort client identifier — IP first, fall back to user pk if logged in."""
    ip = (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR")
        or "unknown"
    )
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return f"user:{user.pk}"
    return f"ip:{ip}"


def rate_limit(
    *,
    scope: str,
    limit: int = 60,
    window_seconds: int = 60,
    key: Callable | None = None,
    block_status: int = 429,
):
    """Decorator that limits a view to ``limit`` calls per ``window_seconds``.

    ``scope`` namespaces the counter so different endpoints don't share quota.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not getattr(settings, "RATE_LIMIT_ENABLED", True):
                return view(request, *args, **kwargs)

            client_id = key(request) if key else _client_id_from_request(request)
            now_int = int(time.time())
            window_start = now_int - (now_int % max(window_seconds, 1))
            cache_key = f"rl:{scope}:{client_id}:{window_start}"

            try:
                added = cache.add(cache_key, 1, timeout=window_seconds + 5)
                if added:
                    count = 1
                else:
                    try:
                        count = cache.incr(cache_key)
                    except ValueError:
                        # Another thread expired the key between add and incr; reset.
                        cache.set(cache_key, 1, timeout=window_seconds + 5)
                        count = 1
            except Exception:
                # Cache backend unavailable — fail open so we don't take the app down.
                return view(request, *args, **kwargs)

            if count > limit:
                retry_after = window_seconds - (now_int - window_start)
                resp = HttpResponse(
                    "Rate limit exceeded. Try again later.",
                    status=block_status,
                    content_type="text/plain",
                )
                resp["Retry-After"] = str(max(retry_after, 1))
                return resp

            return view(request, *args, **kwargs)

        return wrapper

    return decorator


__all__ = ["rate_limit"]
