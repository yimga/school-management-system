"""Migration Cloud reliability primitives.

The user's directive: *Migration Cloud must be an engine that does not fail*.
That requirement decomposes into four operational disciplines:

  1. **HTTP-level idempotency**     — a duplicated POST (flaky network, user
                                       double-click, retry loop) must not run
                                       the underlying mutation twice.
  2. **Bounded retries**             — external calls (AI gateway, SFTP/S3,
                                       SMTP) retry with exponential backoff
                                       + jitter, capped so we never spin
                                       forever.
  3. **Graceful degradation**        — when a dependency is down (AI gateway,
                                       pgvector extension, Celery worker), we
                                       return a partial-but-honest response
                                       rather than a stack trace.
  4. **Status observability**        — every read-side endpoint (progress,
                                       status, list) renders SOMETHING even
                                       when computing the full picture fails.

Pieces 2 already lives in :mod:`apps.migration_cloud.network_resilience`
(tenacity-style retry with exponential backoff + jitter). This module covers
the other three: HTTP idempotency, graceful degradation, observability.

Public surface:
  - :func:`bundle_status_safe`                — always-OK dict for a bundle
  - :func:`request_idempotency_key`           — extract the Idempotency-Key
                                                header per Stripe convention
  - :func:`idempotent_post`                   — decorator caching responses
                                                for 24h keyed on (key, path)
  - :func:`safe_500`                          — decorator turning uncaught
                                                exceptions into structured
                                                JSON 500s with a request_id
  - :func:`with_progress_fallback`            — decorator for progress views:
                                                renders a minimal-but-useful
                                                surface when snapshot fails

All decorators preserve the wrapped view's signature so DRF / Django routing
keeps working. None of them suppress logs; failures are still logged with
``logger.exception`` for ops-side debugging via the usual Sentry / log
pipeline (see ``apps.observability.tracing``).
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import uuid
from typing import Any, Callable

from django.core.cache import cache
from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)


# ─── HTTP-level idempotency ───────────────────────────────────────────────

_IDEMPOTENCY_HEADER = "HTTP_IDEMPOTENCY_KEY"           # Django META key
_IDEMPOTENCY_HEADER_DISPLAY = "Idempotency-Key"        # for docs/Vary
_IDEMPOTENCY_CACHE_TTL_SECONDS = 24 * 60 * 60          # 24h, per Stripe convention
_IDEMPOTENCY_CACHE_KEY_PREFIX = "mc:idem:"
_MAX_KEY_LEN = 255                                     # reject pathological inputs


def request_idempotency_key(request: HttpRequest) -> str | None:
    """Extract the ``Idempotency-Key`` header, or None when missing/malformed.

    Per Stripe's contract: the client supplies a UUID-or-similar opaque token;
    we treat it as a string. We reject empty / overlong keys defensively so a
    misconfigured caller can't fill the cache with garbage.
    """
    raw = request.META.get(_IDEMPOTENCY_HEADER) or ""
    raw = raw.strip()
    if not raw or len(raw) > _MAX_KEY_LEN:
        return None
    # Hash through SHA-256 so the cache key has a fixed shape regardless of
    # what the client sends. Loses no security — clients still see their own
    # token; we just use a derivative internally.
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _idempotency_cache_key(scoped_key: str, request: HttpRequest) -> str:
    """Cache key for ``scoped_key`` on the request's path and tenant.

    Scoping rules (v3.17 hardening, 2026-05-17):
      - **By path:** the same client-supplied Idempotency-Key on a different
        endpoint doesn't collide. Per Stripe's contract, keys are endpoint-scoped.
      - **By tenant + actor:** because the Idempotency-Key is client-chosen
        (a UUID or arbitrary string), two unrelated tenants could pick the
        same value (e.g. ``"retry-1"``). Without tenant scoping, Tenant B's
        request would replay Tenant A's cached response — a cross-tenant data
        leak. We mix the active school's PK into the cache key. Authenticated
        operator/portal requests carry ``request.school`` or ``request.tenant``;
        when neither is present (operator-shell pre-auth or anonymous tooling),
        we fall back to the user PK so concurrent operators don't collide
        either. ``"_"`` is the explicit "no identity" sentinel.
    """
    school = getattr(request, "school", None) or getattr(request, "tenant", None)
    school_pk = getattr(school, "pk", None)
    user_pk = getattr(getattr(request, "user", None), "pk", None)
    actor = school_pk or user_pk or "_"
    return f"{_IDEMPOTENCY_CACHE_KEY_PREFIX}{scoped_key}:{actor}:{request.path}"


def idempotent_post(view_func: Callable) -> Callable:
    """Decorator: short-circuit duplicate POSTs sharing an Idempotency-Key.

    Contract:
      - First request with key K on path P: executes the view, caches the
        response payload + status + content-type for 24h under (K, P).
      - Subsequent request with same K + P inside 24h: returns the cached
        response without re-executing the view.
      - Request without an Idempotency-Key header: executes the view as
        normal (no caching). Idempotency is opt-in per Stripe's pattern.
      - Only POST/PUT/PATCH/DELETE methods are checked. GET passes through.
      - Only 2xx responses are cached. 4xx/5xx are NOT cached so the client
        can retry with the same key after fixing the input.

    Wraps both plain views and CBV ``post()`` methods.
    """

    @functools.wraps(view_func)
    def _wrapped(*args, **kwargs):
        request = _request_from_args(args)
        if request is None or request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return view_func(*args, **kwargs)

        key = request_idempotency_key(request)
        if not key:
            return view_func(*args, **kwargs)

        cache_key = _idempotency_cache_key(key, request)
        cached = cache.get(cache_key)
        if cached is not None:
            # Replay the cached response. Add a marker header so debugging is
            # less painful — operators can see "this was an idempotency replay".
            resp = JsonResponse(
                cached.get("body", {}),
                status=cached.get("status", 200),
                safe=False,
            )
            resp["X-Idempotency-Replay"] = "true"
            resp["Vary"] = _IDEMPOTENCY_HEADER_DISPLAY
            return resp

        resp = view_func(*args, **kwargs)
        # Only cache JSON 2xx responses; other content types (HTML, SSE) are
        # not idempotency-friendly. We also skip caching when the response is
        # already a redirect — those are inherently re-issuable.
        if 200 <= getattr(resp, "status_code", 500) < 300:
            try:
                body = json.loads(resp.content.decode("utf-8"))
            except (ValueError, AttributeError, UnicodeDecodeError):
                body = None
            if body is not None:
                cache.set(
                    cache_key,
                    {"body": body, "status": resp.status_code},
                    timeout=_IDEMPOTENCY_CACHE_TTL_SECONDS,
                )
        resp["Vary"] = _IDEMPOTENCY_HEADER_DISPLAY
        return resp

    return _wrapped


def _request_from_args(args: tuple) -> HttpRequest | None:
    """Pull the HttpRequest out of a view's args tuple regardless of CBV/FBV shape."""
    if not args:
        return None
    # FBV: (request, ...) → args[0] is request
    # CBV: (self, request, ...) → args[1] is request
    if isinstance(args[0], HttpRequest):
        return args[0]
    if len(args) > 1 and isinstance(args[1], HttpRequest):
        return args[1]
    return None


# ─── Structured 500 envelope ─────────────────────────────────────────────


def safe_500(view_func: Callable) -> Callable:
    """Decorator: any uncaught exception → JSON 500 with a ``request_id``.

    Operators copy the request_id into the support ticket; ops correlates with
    the Sentry trace + log line. Stack traces never leak to the client.

    Status-code semantics preserved: the wrapped view's own JsonResponse error
    paths (404/409/etc.) pass through untouched. Only true 500-class exceptions
    get the envelope treatment.
    """

    @functools.wraps(view_func)
    def _wrapped(*args, **kwargs):
        _request_from_args(args)
        try:
            return view_func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — defensive boundary
            request_id = uuid.uuid4().hex[:16]
            logger.exception(
                "migration_cloud.reliability: unhandled exception in %s [%s]",
                view_func.__name__, request_id,
            )
            # Echo only the exception CLASS name to the client — never the
            # message body. Exception messages can carry sensitive context
            # (file paths, SQL fragments, secret fragments) that the operator
            # UI would render and that ops logs would mirror to support
            # tickets. The full message + traceback is captured by the
            # logger.exception call above and routed to Sentry / log
            # pipeline, where it stays inside the trust boundary.
            return JsonResponse(
                {
                    "error": "internal_error",
                    "error_class": exc.__class__.__name__,
                    "request_id": request_id,
                    "remediation": (
                        "Retry the request. If the issue persists, copy the "
                        "request_id and open a support ticket — operations "
                        "can correlate it with the trace."
                    ),
                },
                status=500,
            )

    return _wrapped


# ─── Always-OK bundle status ─────────────────────────────────────────────


def bundle_status_safe(bundle) -> dict[str, Any]:
    """Return a serializable status dict that NEVER raises.

    Used by the progress view + status endpoints so a half-broken bundle
    (NULL fields, missing related rows, downstream computation crash) still
    surfaces *something* to the operator. Each section is computed in its
    own try/except so one section failing doesn't blank the whole response.

    Output shape (all keys always present):
        {
          "bundle_id": int | None,
          "label": str,
          "status": str,
          "idempotency_key": str,
          "school_id": int | None,
          "intake_method": str,
          "source_hint": str,
          "size_summary": dict,
          "totals": {"artifacts": int, "rows": int, "errors": int},
          "recent_events": list[dict],   (best-effort, may be [])
          "warnings": list[str],          (degraded-section markers)
        }
    """
    out: dict[str, Any] = {
        "bundle_id": getattr(bundle, "pk", None) or getattr(bundle, "id", None),
        "label": "",
        "status": "unknown",
        "idempotency_key": "",
        "school_id": None,
        "intake_method": "",
        "source_hint": "",
        "size_summary": {},
        "totals": {"artifacts": 0, "rows": 0, "errors": 0},
        "recent_events": [],
        "warnings": [],
    }

    # Section 1 — flat scalar fields. Each guarded.
    for field, default in (
        ("label", ""),
        ("status", "unknown"),
        ("idempotency_key", ""),
        ("intake_method", ""),
        ("source_hint", ""),
    ):
        try:
            out[field] = getattr(bundle, field, default) or default
        except Exception:  # noqa: BLE001
            out["warnings"].append(f"could not read field {field}")

    # Section 2 — school_id (FK; .school_id avoids a related query).
    try:
        out["school_id"] = getattr(bundle, "school_id", None)
    except Exception:  # noqa: BLE001
        out["warnings"].append("could not read school_id")

    # Section 3 — size_summary (JSONField; may be NULL, may be malformed).
    try:
        summary = getattr(bundle, "size_summary", None) or {}
        if isinstance(summary, dict):
            out["size_summary"] = summary
        else:
            out["warnings"].append("size_summary not a dict; ignored")
    except Exception:  # noqa: BLE001
        out["warnings"].append("could not read size_summary")

    # Section 4 — totals (artifact + row counters; aggregate, may be slow).
    try:
        artifacts = getattr(bundle, "artifacts", None)
        if artifacts is not None:
            out["totals"]["artifacts"] = artifacts.count()
    except Exception:  # noqa: BLE001
        out["warnings"].append("could not count artifacts")

    # Section 5 — recent progress events (best-effort).
    try:
        events_qs = getattr(bundle, "progress_events", None)
        if events_qs is not None:
            out["recent_events"] = [
                {
                    "id": ev.id,
                    "kind": ev.kind,
                    "stage": ev.stage,
                    "message": ev.message,
                    "created_at": (
                        ev.created_at.isoformat() if ev.created_at else None
                    ),
                }
                for ev in events_qs.order_by("-created_at")[:20]
            ]
    except Exception:  # noqa: BLE001
        out["warnings"].append("could not read recent_events")

    return out


# ─── Progress view fallback decorator ─────────────────────────────────────


def with_progress_fallback(view_func: Callable) -> Callable:
    """Decorator for progress views: never 500, always render *something*.

    If the wrapped view raises, we re-fetch the bundle row directly (bypassing
    snapshot computation) and render a degraded progress page that surfaces
    the bundle's basic identity + the warnings from :func:`bundle_status_safe`.
    The operator sees "we know your bundle exists; here's what we couldn't
    compute" instead of a generic 500.

    Note: this decorator assumes the wrapped view accepts ``bundle_id`` as a
    URL kwarg. That's the contract for every progress-shaped view in this
    namespace.
    """

    @functools.wraps(view_func)
    def _wrapped(*args, **kwargs):
        try:
            return view_func(*args, **kwargs)
        except Exception:  # noqa: BLE001
            request = _request_from_args(args)
            bundle_id = kwargs.get("bundle_id")
            shell = kwargs.get("shell", "super")
            request_id = uuid.uuid4().hex[:16]
            logger.exception(
                "migration_cloud.reliability: progress fallback engaged [bundle=%s, request_id=%s]",
                bundle_id, request_id,
            )

            # Try to render the degraded template; if even that fails, return
            # a JSON 200 envelope so the operator at least gets something back.
            try:
                from .models import MigrationBundle
                from django.shortcuts import render

                bundle = MigrationBundle.objects.filter(pk=bundle_id).first()  # tenant-isolation-allow: PK lookup by internal bundle id
                if bundle is None:
                    return JsonResponse(
                        {
                            "error": "bundle_not_found",
                            "bundle_id": bundle_id,
                            "request_id": request_id,
                        },
                        status=404,
                    )
                status = bundle_status_safe(bundle)
                status["request_id"] = request_id
                if request and request.GET.get("format") == "json":
                    return JsonResponse(
                        {
                            "bundle_id": bundle.pk,
                            "degraded": True,
                            "snapshot": status,
                            "request_id": request_id,
                        },
                        status=200,
                    )
                return render(
                    request,
                    "migration_cloud/progress.html",
                    {
                        # Keep the degraded page inside the tenant shell too — a
                        # snapshot failure must not leak the operator chrome to a
                        # portal user. Inlined (not _mc_base_for_shell) to avoid a
                        # circular import: views.py imports this module.
                        "mc_base": (
                            "migration_cloud/_mc_base_portal.html"
                            if shell == "portal"
                            else "control_plane_base.html"
                        ),
                        "shell": shell,
                        "bundle": bundle,
                        "snapshot": None,
                        "degraded_status": status,
                        "request_id": request_id,
                        "page_title": (
                            f"Progress — {status.get('label') or status.get('idempotency_key') or bundle.pk}"
                        ),
                    },
                    status=200,
                )
            except Exception:  # noqa: BLE001 — total fallback
                logger.exception("migration_cloud.reliability: progress fallback render itself failed")
                return JsonResponse(
                    {
                        "error": "progress_unavailable",
                        "bundle_id": bundle_id,
                        "request_id": request_id,
                        "remediation": (
                            "Migration Cloud progress is temporarily unavailable. "
                            "The bundle exists and your data is safe. Retry shortly "
                            "or open a support ticket with the request_id."
                        ),
                    },
                    status=200,
                )

    return _wrapped
