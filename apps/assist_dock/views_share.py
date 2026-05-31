"""v4.00.95 Wave E5 — share short-link endpoints."""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
    JsonResponse,
)
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_safe

from .short_links import (
    SHORT_LINK_DEFAULT_TTL_HOURS,
    SHORT_LINK_MAX_TTL_HOURS,
    mint_short_link,
    record_short_link_hit,
    resolve_short_link,
)

logger = logging.getLogger(__name__)

_MAX_MINT_BODY_BYTES = 4 * 1024


@login_required
@require_http_methods(["POST"])
@csrf_protect
def mint_share_link(request):
    """Body: ``{"target": "/portal/dashboard/", "ttl_hours": 24}``."""
    raw = request.body or b""
    if len(raw) > _MAX_MINT_BODY_BYTES:
        return HttpResponseBadRequest("payload too large")
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("bad json")
    if not isinstance(body, dict):
        return HttpResponseBadRequest("body must be object")
    target = str(body.get("target") or "")
    ttl_hours = body.get("ttl_hours", SHORT_LINK_DEFAULT_TTL_HOURS)
    try:
        ttl_hours = int(ttl_hours)
    except (TypeError, ValueError):
        ttl_hours = SHORT_LINK_DEFAULT_TTL_HOURS
    link, err = mint_short_link(
        target_url=target, created_by=request.user, ttl_hours=ttl_hours
    )
    if link is None:
        return JsonResponse({"ok": False, "error": err}, status=400)
    short_path = "/assist-dock/s/" + link.token + "/"
    absolute = request.build_absolute_uri(short_path)
    return JsonResponse(
        {
            "ok": True,
            "token": link.token,
            "short_path": short_path,
            "short_url": absolute,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            "ttl_hours_max": SHORT_LINK_MAX_TTL_HOURS,
        }
    )


@require_safe
def resolve_share_link(request, token):
    """Public 302 redirect to the saved target URL — gone after expiry.

    Note: no @login_required here so a recipient who isn't on the platform
    can still follow the link; the underlying target enforces its own auth.
    """
    link = resolve_short_link(token)
    if link is None:
        return HttpResponse("Link expired or not found.", status=410)
    record_short_link_hit(link)
    target = link.target_url
    if not target:
        return HttpResponse("Link malformed.", status=410)
    return HttpResponseRedirect(target)
