"""v4.00.96 Wave F2 — wave/ping chat handoff between co-viewers.

The ``presence`` chip lists other operators on the current page. F2 lets
the viewer "wave at" another operator: a tiny Insight is pushed to the
target user's copilot ring, the ai-copilot chip's badge promotes, and
clicking it lands a short message + a deep-link back to the page where
the wave originated.

This is the lightweight cousin of co-browse — no WebSocket, no realtime
voice, just an asynchronous nudge that fits the existing infrastructure.
"""

from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from services.http_auth_guards import login_required_api as login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .insights import INSIGHT_INFO, Insight, push_insight
from .presence import list_present

logger = logging.getLogger(__name__)

_MAX_BODY_BYTES = 2 * 1024  # magic-number-allow: byte-size-cap
_WAVE_RATE_LIMIT_SECONDS = 30
_WAVE_INSIGHT_TTL_SECONDS = 30 * 60

# In-process rate limiter — key = (sender_user_id, target_user_id, page).
_LAST_WAVE_AT: dict[tuple, float] = {}


def _display_label(user) -> str:
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
    return "An operator"


def _rate_limited(key: tuple, now: float) -> bool:
    last = _LAST_WAVE_AT.get(key)
    if last is not None and (now - last) < _WAVE_RATE_LIMIT_SECONDS:
        return True
    _LAST_WAVE_AT[key] = now
    # Best-effort prune so the dict doesn't grow unbounded.
    if len(_LAST_WAVE_AT) > 5000:  # magic-number-allow: in-memory-ring-buffer-cap
        cutoff = now - 600  # magic-number-allow: cooldown-window-seconds
        stale = [k for k, t in _LAST_WAVE_AT.items() if t < cutoff]
        for k in stale:
            _LAST_WAVE_AT.pop(k, None)
    return False


@login_required
@require_http_methods(["POST"])
@csrf_protect
def wave_at_view(request):
    """Body: ``{"target_user_id": 99, "page_path": "/finance/", "note": "..."}``.

    Pushes an Insight to the target user. The note is short, optional,
    and stripped of control chars. Rate-limited at one wave per
    (sender, target, page) per 30s to prevent harassment.
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

    try:
        target_user_id = int(body.get("target_user_id") or 0)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("target_user_id must be int")
    if target_user_id <= 0:
        return HttpResponseBadRequest("target_user_id required")

    page_path = str(body.get("page_path") or "")[:256]
    if not page_path:
        return HttpResponseBadRequest("page_path required")

    note = str(body.get("note") or "")[:200]
    note = "".join(ch for ch in note if ch >= " " and ch != "\x7f")

    sender = request.user
    sender_id = getattr(sender, "pk", 0) or 0
    if sender_id == target_user_id:
        return HttpResponseBadRequest("cannot wave at yourself")

    # Verify the target is actually on the page (anti-spam: only people
    # the sender can see in their presence list can be waved at).
    present = list_present(page_path=page_path, exclude_user_id=sender_id)
    if target_user_id not in {e.user_id for e in present}:
        return HttpResponseForbidden("target not co-viewing this page")

    now = time.time()
    key = (sender_id, target_user_id, page_path)
    if _rate_limited(key, now):
        return JsonResponse(
            {"ok": False, "error": "rate_limited", "retry_after_seconds": _WAVE_RATE_LIMIT_SECONDS},
            status=429,
        )

    sender_label = _display_label(sender)
    insight_id = f"wave-{sender_id}-{uuid4().hex[:8]}"
    insight_body = note if note else f"{sender_label} is looking at this page too."
    push_insight(
        target_user_id,
        Insight(
            id=insight_id,
            title=f"{sender_label} waved",
            body=insight_body,
            level=INSIGHT_INFO,
            page_path=page_path,
            cta_label="Open page",
            cta_href=page_path,
            expires_at=now + _WAVE_INSIGHT_TTL_SECONDS,
        ),
    )
    return JsonResponse({"ok": True, "insight_id": insight_id})


def reset_rate_limiter_for_tests() -> None:
    _LAST_WAVE_AT.clear()
