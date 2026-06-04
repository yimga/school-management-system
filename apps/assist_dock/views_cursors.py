"""v4.00.97 Wave G1 — cursor co-browse endpoints.

POST /assist-dock/cursors/heartbeat/  →  record cursor position
GET  /assist-dock/cursors/list.json   →  list peer cursors on a page

In-memory only (no DB write — cursors are highly volatile at 4 Hz and
would dominate write traffic). Cross-worker visibility is best-effort:
two workers see each other's cursor lists when both clients are on the
same page AND happen to land on the same worker for either request,
which is the common shape on small deployments.
"""

from __future__ import annotations

import json
import logging

from services.http_auth_guards import login_required_api as login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_safe

from .cursors import (
    CURSOR_HEARTBEAT_SECONDS,
    CURSOR_TTL_SECONDS,
    heartbeat,
    list_cursors,
    pings_as_jsonable,
)

logger = logging.getLogger(__name__)

_MAX_BODY_BYTES = 1024  # magic-number-allow: byte-size-cap


def _display_name(user) -> str:
    for attr in ("get_short_name", "get_full_name"):
        getter = getattr(user, attr, None)
        if callable(getter):
            try:
                value = getter()
                if value:
                    return str(value)[:80]
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue
    for attr in ("username", "email"):
        value = getattr(user, attr, "") or ""
        if value:
            return str(value)[:80]
    return ""


@login_required
@require_http_methods(["POST"])
@csrf_protect
def cursor_heartbeat(request):
    """Record / refresh the caller's cursor on ``page_path``.

    Body: ``{"page_path": "/portal/x/", "x_pct": 42.1, "y_pct": 18.7,
              "selection_text": "..."}``.
    """
    raw = request.body or b""
    if len(raw) > _MAX_BODY_BYTES:
        return HttpResponseBadRequest("payload too large")
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("bad json")
    if not isinstance(body, dict):
        return HttpResponseBadRequest("body must be object")
    page_path = str(body.get("page_path") or "")[:256]
    if not page_path:
        return HttpResponseBadRequest("page_path required")
    user = request.user
    ping = heartbeat(
        user_id=user.pk,
        page_path=page_path,
        x_pct=body.get("x_pct", 0.0),
        y_pct=body.get("y_pct", 0.0),
        display_name=_display_name(user),
        selection_text=body.get("selection_text", ""),
    )
    return JsonResponse(
        {
            "ok": True,
            "heartbeat_seconds": CURSOR_HEARTBEAT_SECONDS,
            "ttl_seconds": CURSOR_TTL_SECONDS,
            "last_seen": ping.last_seen if ping else None,
        }
    )


@login_required
@require_safe
def cursor_list(request):
    """Return active cursor pings on ``?page=<path>`` excluding the caller."""
    page_path = (request.GET.get("page") or "")[:256]
    user_id = getattr(request.user, "pk", None) or 0
    pings = list_cursors(page_path=page_path, exclude_user_id=user_id)
    return JsonResponse(
        {
            "count": len(pings),
            "page_path": page_path,
            "cursors": pings_as_jsonable(pings),
        }
    )
