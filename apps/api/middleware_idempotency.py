"""
Pass 12.B: global Idempotency-Key middleware for the public API.

When a request to /api/v1/ (POST / PATCH / PUT / DELETE) carries an
`Idempotency-Key` header, the middleware:

  1. Looks up `idem:<tenant>:<user>:<method>:<path>:<key>` in the cache.
  2. If a stored response exists for that key, returns it verbatim.
  3. Otherwise runs the view, then stores `(status, headers, body)` in the
     cache with a 24h TTL.

Only HTTP responses with a JSON body are cached, and only on success
(2xx) — error responses fall through so the client can retry after a fix.
Cache backend is whatever `django.core.cache` is configured with (Redis in
production, locmem in tests).

Scope is intentionally narrow: only requests under `/api/v1/` and only when
the client opts in by supplying the header. This matches Stripe / GitHub /
Twilio idempotency semantics and avoids accidentally deduplicating writes
from internal Django views.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24h
APPLICABLE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
URL_PREFIX = "/api/v1/"


def _ttl() -> int:
    try:
        return int(getattr(settings, "API_IDEMPOTENCY_TTL_SECONDS", DEFAULT_TTL_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_TTL_SECONDS


def _user_key(request) -> str:
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return f"u{user.pk}"
    return "anon"


def _tenant_key(request) -> str:
    school = getattr(request, "school", None)
    if school is not None and getattr(school, "id", None) is not None:
        return f"s{school.id}"
    return "global"


def _cache_key(request, header_value: str) -> str:
    raw = (
        f"{_tenant_key(request)}:{_user_key(request)}:{request.method}:"
        f"{request.path}:{header_value}"
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]
    return f"idem:{digest}"


def _serializable_response(response: HttpResponse) -> dict[str, Any] | None:
    """Return a plain dict snapshot of the response, or None if not cacheable."""
    if not 200 <= response.status_code < 300:
        return None
    content_type = response.get("Content-Type", "") or ""
    # Only cache JSON / problem+json bodies; HTML / streaming / files are out.
    if "json" not in content_type.lower():
        return None
    try:
        body = response.content.decode("utf-8")
    except (AttributeError, UnicodeDecodeError):
        return None
    return {
        "status": int(response.status_code),
        "content_type": content_type,
        "body": body,
    }


def _replay_response(snapshot: dict[str, Any]) -> HttpResponse:
    body = snapshot.get("body", "")
    response = HttpResponse(
        body,
        status=int(snapshot.get("status", 200)),
        content_type=snapshot.get("content_type") or "application/json",
    )
    response["Idempotent-Replay"] = "1"
    return response


class IdempotencyKeyMiddleware:
    """
    Process_request stage looks up a cached snapshot; process_response stores
    a fresh one. No-op for unrelated paths / methods / missing header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        key = self._extract_key(request)
        if not key:
            return self.get_response(request)

        cache_key = _cache_key(request, key)
        try:
            cached = cache.get(cache_key)
        except Exception:  # noqa: BLE001 - cache failure must not block writes
            cached = None
        if cached:
            return _replay_response(cached)

        response = self.get_response(request)

        snapshot = _serializable_response(response)
        if snapshot is not None:
            try:
                cache.set(cache_key, snapshot, _ttl())
            except Exception:  # noqa: BLE001 - cache failure must not break the response
                logger.debug("idempotency cache.set failed for %s", cache_key)
        return response

    def _extract_key(self, request) -> str:
        if request.method not in APPLICABLE_METHODS:
            return ""
        if not request.path.startswith(URL_PREFIX):
            return ""
        header = (
            request.META.get("HTTP_IDEMPOTENCY_KEY")
            or request.META.get("HTTP_X_IDEMPOTENCY_KEY")
            or ""
        )
        header = header.strip()
        if not header:
            return ""
        # Defensive: cap at 200 chars to avoid pathological cache-key sizes.
        return header[:200]
