"""v4.00.91 — assist dock views.

Wave A ships ``registry_introspect`` (staff-only) so operators can verify
what chips will render on a given surface. Wave B adds ``dock_context_view``
— per-page JSON the JS polls for live badges + quick actions. Wave E3
adds ``dock_context_stream_view`` — SSE upgrade so badges land in <1s
instead of <60s.
"""

from __future__ import annotations

import json
import logging
import time

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from services.http_auth_guards import login_required_api as login_required
from services.sse_response import guarded_sse_response
from django.views.decorators.http import require_safe

from .badges import resolve_all_badges
from .context_processors import _resolve_role, _resolve_surface
from .cursors import list_cursors, pings_as_jsonable
from .quick_actions import actions_as_jsonable, actions_for
from .registry import all_slots, get_slots_for, slots_as_jsonable
from .tools_tray_page_context import build_tools_tray_page_payload

logger = logging.getLogger(__name__)

# SSE stream parameters — keep the connection cheap (must release WSGI threads).
_SSE_TICK_SECONDS = 5
_SSE_HEARTBEAT_SECONDS = 25


def _sse_max_duration_seconds() -> float:
    from services.sse_wsgi_limits import wsgi_sse_max_duration_seconds

    return wsgi_sse_max_duration_seconds(
        env_key="ASSIST_DOCK_SSE_MAX_SECONDS",
        default_seconds=25.0,
    )


def _sse_max_frames() -> int:
    duration = _sse_max_duration_seconds()
    return max(12, int(duration / _SSE_TICK_SECONDS) + 4)

# Cap quick-action count returned per request so a runaway registry never
# floods the dock chrome.
_QUICK_ACTIONS_LIMIT = 6

# Max length we accept for ?page= so the JSON response stays bounded.
_PAGE_PATH_MAX_LEN = 256


@staff_member_required
@require_safe
def registry_introspect(request):
    """Return the full registry snapshot. Staff-only.

    Filter by `?surface=portal|manager|admin` and/or `?role=...`.
    """
    surface = (request.GET.get("surface") or "*").strip()
    role = (request.GET.get("role") or "*").strip()
    include_hidden = request.GET.get("include_hidden") in {"1", "true", "yes"}

    if surface == "*" and role == "*" and include_hidden:
        slots = all_slots()
        slots.sort(key=lambda s: (s.order, s.id))
    else:
        slots = get_slots_for(
            surface=surface, role=role, include_hidden=include_hidden
        )
    return JsonResponse(
        {
            "count": len(slots),
            "surface": surface,
            "role": role,
            "slots": slots_as_jsonable(slots),
        }
    )


def _sanitize_page_path(raw: str) -> str:
    """Trim to a safe, length-bounded path string.

    The page path is *advisory* (used to filter quick actions + tag the
    predictive halo on the client). We never trust it for permission
    decisions, so simple length + control-char cleanup is enough.
    """
    if not raw:
        return ""
    raw = raw[: _PAGE_PATH_MAX_LEN]
    return "".join(ch for ch in raw if ch >= " " and ch != "\x7f")


@require_safe
def dock_context_view(request):
    """Per-page JSON the JS polls for badges + quick actions.

    Authenticated users only. Anonymous returns an empty payload (no
    badges to leak, no quick actions to surface). The payload schema:

        {
          "surface": "portal",
          "role": "TEACHER",
          "page_path": "/portal/dashboard/",
          "badges": {<slot_id>: {count, dot, level, tooltip}},
          "quick_actions": [{id, label, icon, href, description, order}],
          "polled_at": "2026-05-30T15:00:00Z"
        }
    """
    if not getattr(request.user, "is_authenticated", False):
        return JsonResponse(
            {
                "surface": "*",
                "role": "anonymous",
                "page_path": "",
                "badges": {},
                "quick_actions": [],
                "tools_tray": {},
            }
        )

    surface = _resolve_surface(request)
    role = _resolve_role(request)
    page_path = _sanitize_page_path(request.GET.get("page", ""))

    slots = get_slots_for(surface=surface, role=role)
    badges = resolve_all_badges(request, slots=slots, page_path=page_path)
    quick = actions_for(
        surface=surface,
        role=role,
        page_path=page_path,
        limit=_QUICK_ACTIONS_LIMIT,
    )
    from .tools_tray_page_context import build_tools_tray_page_payload

    tools_tray = build_tools_tray_page_payload(request, page_path=page_path)
    return JsonResponse(
        {
            "surface": surface,
            "role": role,
            "page_path": page_path,
            "badges": badges,
            "quick_actions": actions_as_jsonable(quick),
            "tools_tray": tools_tray,
        }
    )


def _sse_pack(event: str, data: dict) -> bytes:
    """Encode a single SSE frame. ``event:`` then ``data:`` lines, blank end."""
    body = json.dumps(data, separators=(",", ":"))
    chunk = f"event: {event}\ndata: {body}\n\n"
    return chunk.encode("utf-8")


@login_required(sse=True)
@require_safe
def dock_context_stream_view(request):
    """SSE stream for badge / quick-action push (WSGI-safe sync generator).

    Mirrors ``workflow_progress.stream_view``: a sync byte generator so Gunicorn
    gthread workers on Render stream reliably. The JSON poller
    (``/assist-dock/context.json``) remains the client fallback.
    """

    surface = _resolve_surface(request)
    role = _resolve_role(request)
    page_path = _sanitize_page_path(request.GET.get("page", ""))
    user_id = getattr(request.user, "pk", None) or 0

    def _stream():
        slots = get_slots_for(surface=surface, role=role)
        try:
            initial_badges = resolve_all_badges(
                request, slots=slots, page_path=page_path
            )
            quick = actions_for(
                surface=surface,
                role=role,
                page_path=page_path,
                limit=_QUICK_ACTIONS_LIMIT,
            )
            yield _sse_pack(
                "snapshot",
                {
                    "surface": surface,
                    "role": role,
                    "page_path": page_path,
                    "badges": initial_badges,
                    "quick_actions": actions_as_jsonable(quick),
                    "tools_tray": build_tools_tray_page_payload(
                        request, page_path=page_path
                    ),
                },
            )
        except Exception as exc:  # noqa: BLE001 — never tear down the stream
            logger.debug("SSE snapshot failed: %s", exc)
            yield _sse_pack("error", {"code": "snapshot_failed"})
            yield _sse_pack("done", {})
            return

        prev_badges = initial_badges
        prev_cursors_key = None
        last_hb = time.time()
        started_at = time.time()
        frames = 0
        while True:
            now = time.time()
            if now - started_at > _sse_max_duration_seconds():
                break
            if frames > _sse_max_frames():
                break
            try:
                next_badges = resolve_all_badges(
                    request, slots=slots, page_path=page_path
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("SSE tick resolve failed: %s", exc)
                next_badges = prev_badges
            cursor_payload = []
            cursors_key = ""
            if page_path:
                try:
                    cursor_pings = list_cursors(
                        page_path=page_path, exclude_user_id=user_id
                    )
                    cursor_payload = pings_as_jsonable(cursor_pings)
                    cursors_key = "|".join(
                        f"{p['user_id']}:{p['x_pct']:.1f}:{p['y_pct']:.1f}"
                        for p in cursor_payload
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("SSE cursor resolve failed: %s", exc)
                    cursor_payload = []
                    cursors_key = prev_cursors_key or ""
            if next_badges != prev_badges:
                yield _sse_pack("badges", {"badges": next_badges})
                prev_badges = next_badges
                last_hb = now
            if cursors_key != prev_cursors_key:
                yield _sse_pack("cursors", {"cursors": cursor_payload})
                prev_cursors_key = cursors_key
                last_hb = now
            if now - last_hb >= _SSE_HEARTBEAT_SECONDS:
                yield _sse_pack("heartbeat", {"ts": int(now)})
                last_hb = now
            frames += 1
            time.sleep(_SSE_TICK_SECONDS)
        yield _sse_pack("done", {})

    return guarded_sse_response(_stream, content_type="text/event-stream")
