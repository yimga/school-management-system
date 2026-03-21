"""
Real-user monitoring (RUM) ingest: browser beacons Web Vitals–shaped metrics.

CSRF-exempt POST with shared token (body `token` or header X-RUM-Key) so sendBeacon works.
Disabled when settings.RUM_INGEST_KEY is unset or shorter than 16 chars.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.platform_runtime.events import emit_platform_event

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 4096
RATE_LIMIT_PER_HOUR = 120
ALLOWED_METRIC_KEYS = frozenset(
    {"lcp", "cls", "inp", "fcp", "ttfb", "fid", "tbt", "nav"}
)


def _rum_rate_ok(request) -> bool:
    ip = request.META.get("REMOTE_ADDR") or "0"
    ck = f"rum:rl:{ip}"
    try:
        cache.add(ck, 0, timeout=3600)
    except Exception:
        logger.debug("rum rate cache add failed", exc_info=True)
    try:
        n = cache.incr(ck)
    except ValueError:
        cache.set(ck, 1, timeout=3600)
        n = 1
    return n <= RATE_LIMIT_PER_HOUR


def _sanitize_metrics(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in list(raw.items())[:24]:
        ks = str(k)[:32]
        if ks not in ALLOWED_METRIC_KEYS:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if not (-1e9 < fv < 1e9):
            continue
        out[ks] = round(fv, 4)
    return out


@csrf_exempt
@require_POST
def rum_ingest(request):
    """Ingest RUM JSON; auth via body token or X-RUM-Key (see csrf_exempt allowlist)."""
    configured = (getattr(settings, "RUM_INGEST_KEY", None) or "").strip()
    if len(configured) < 16:
        return HttpResponse(status=404)

    if len(request.body) > MAX_BODY_BYTES:
        return HttpResponse(status=413)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse(status=400)

    if not isinstance(data, dict):
        return HttpResponse(status=400)

    sent = (
        (data.get("token") if isinstance(data.get("token"), str) else None)
        or request.headers.get("X-RUM-Key")
        or request.META.get("HTTP_X_RUM_KEY")
        or ""
    ).strip()
    if len(sent) != len(configured) or not secrets.compare_digest(sent, configured):
        return HttpResponse(status=403)

    if not _rum_rate_ok(request):
        return HttpResponse(status=429)

    path = str(data.get("path") or "")[:256]
    nav_type = str(data.get("navigation_type") or "")[:64]
    metrics = _sanitize_metrics(data.get("metrics"))

    emit_platform_event(
        "rum_web_vitals",
        {
            "path": path,
            "metrics": metrics,
            "navigation_type": nav_type,
        },
        tenant_id="",
    )
    return HttpResponse(status=204)
