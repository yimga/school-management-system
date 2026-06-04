"""v4.00.95 Wave E1 — presence endpoints."""

from __future__ import annotations

import json
import logging

from services.http_auth_guards import login_required_api as login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_safe

from .presence import (
    PRESENCE_HEARTBEAT_SECONDS,
    entries_as_jsonable,
    heartbeat,
    list_present,
)

logger = logging.getLogger(__name__)

_MAX_BODY_BYTES = 1024  # magic-number-allow: byte-size-cap


def _display_name(user) -> str:
    for attr in ("get_full_name", "get_short_name"):
        getter = getattr(user, attr, None)
        if callable(getter):
            try:
                value = getter()
                if value:
                    return str(value)[:80]
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
    for attr in ("username", "email"):
        value = getattr(user, attr, "") or ""
        if value:
            return str(value)[:80]
    return ""


def _avatar_url(user) -> str:
    for attr in ("avatar_url", "profile_avatar_url", "photo_url"):
        value = getattr(user, attr, "") or ""
        if value:
            return str(value)[:512]
    return ""


@login_required
@require_http_methods(["POST"])
@csrf_protect
def presence_heartbeat(request):
    """Record the requesting user's presence on the given page.

    Body: ``{"page_path": "/portal/dashboard/"}``.
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
    entry = heartbeat(
        user_id=user.pk,
        page_path=page_path,
        display_name=_display_name(user),
        avatar_url=_avatar_url(user),
    )
    return JsonResponse(
        {
            "ok": True,
            "heartbeat_seconds": PRESENCE_HEARTBEAT_SECONDS,
            "first_seen": entry.first_seen if entry else None,
        }
    )


@login_required
@require_safe
def presence_list(request):
    """Return active presence entries on ``?page=<path>`` (excludes self)."""
    page_path = (request.GET.get("page") or "")[:256]
    user_id = getattr(request.user, "pk", None) or 0
    entries = list_present(page_path=page_path, exclude_user_id=user_id)
    return JsonResponse(
        {
            "count": len(entries),
            "page_path": page_path,
            "present": entries_as_jsonable(entries),
        }
    )
