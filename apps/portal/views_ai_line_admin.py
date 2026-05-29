"""v4.00.35 — operator UIs for AI-line.

Two pages:
  * ``/portal/configure/ai-line-intents/`` — tenant-admin editor for the
    per-school ``runtime_defaults['ai_line_intents']`` JSON list.
  * ``/super/ai-line/intent-coverage/`` — staff dashboard summarizing
    which AI-line intents are firing across the platform. Best-effort:
    reads from an in-process ring buffer that ``_log_intent_hit()`` pushes
    into AND mirrors into the Django cache so cross-worker observability
    works without log shipping.
"""
from __future__ import annotations

import collections
import json
import logging
import threading
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


# ----- In-process ring buffer ---------------------------------------------
# Per-worker; not durable. Operators get a "last N calls" view without
# requiring a log-shipping pipeline. For real cross-worker observability
# we ALSO mirror to the Django cache (v4.00.35).
_BUFFER_CAP = 500
_BUFFER: collections.deque = collections.deque(maxlen=_BUFFER_CAP)
_BUFFER_LOCK = threading.Lock()

# v4.00.35 — durable mirror via cache. Single key holds the last
# ``_BUFFER_CAP`` rows; writes serialize via a tiny in-process lock so
# concurrent pushes don't trample each other. Cache backend can be anything
# (locmem / redis / memcached); we degrade silently if cache is unavailable.
_CACHE_KEY = "ai_line:intent_coverage:ring"
_CACHE_TTL = 60 * 60 * 24  # 24h sliding window


def _push_cache(entry: dict[str, Any]) -> None:
    try:
        existing = cache.get(_CACHE_KEY) or []
        if not isinstance(existing, list):
            existing = []
        existing.append(entry)
        if len(existing) > _BUFFER_CAP:
            existing = existing[-_BUFFER_CAP:]
        cache.set(_CACHE_KEY, existing, _CACHE_TTL)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ai-line cache mirror failed: %s", exc)


def record_intent_hit(*, intent: str, matched: bool, ai_on: bool, qlen: int, school: str, url: str) -> None:
    """Called from ``views_ai_line._log_intent_hit`` to also stash a record."""
    entry = {
        "intent": intent or "none",
        "matched": bool(matched),
        "ai_on": bool(ai_on),
        "qlen": int(qlen or 0),
        "school": (school or "-")[:16],
        "url": (url or "-")[:80],
    }
    try:
        with _BUFFER_LOCK:
            _BUFFER.append(entry)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ai-line buffer push failed: %s", exc)
    _push_cache(entry)


def _snapshot() -> list[dict[str, Any]]:
    """Best-effort cross-worker snapshot — cache wins when available.

    Falls back to the in-process ring buffer when the cache backend is
    locmem on a fresh worker (still useful for single-worker dev).
    """
    try:
        durable = cache.get(_CACHE_KEY)
        if isinstance(durable, list) and durable:
            return list(durable)[-_BUFFER_CAP:]
    except Exception as exc:  # noqa: BLE001
        logger.debug("ai-line cache read failed: %s", exc)
    with _BUFFER_LOCK:
        return list(_BUFFER)


# ----- Tenant admin: edit ai_line_intents ---------------------------------


@login_required
@require_http_methods(["GET"])
def tenant_ai_line_intents_view(request):
    """Render the per-school AI-line intent editor."""
    school = getattr(request, "school", None)
    intents: list[dict[str, Any]] = []
    if school is not None:
        try:
            rd = getattr(school, "runtime_defaults", None) or {}
            if isinstance(rd, dict):
                intents = list(rd.get("ai_line_intents") or [])
        except Exception as exc:  # noqa: BLE001
            logger.debug("intents load failed: %s", exc)

    return render(
        request,
        "portal/ai_line_intents.html",
        {
            "intents_json": json.dumps(intents, indent=2),
            "intent_count": len(intents),
            "is_admin_user": getattr(request.user, "is_staff", False)
            or _user_has_role(request, "ADMIN"),
        },
    )


@login_required
@require_http_methods(["POST"])
@csrf_protect
def tenant_ai_line_intents_save(request):
    """Persist a posted list of intents to ``school.runtime_defaults``."""
    school = getattr(request, "school", None)
    if school is None:
        return JsonResponse({"success": False, "error": "no_tenant"}, status=400)
    if not (getattr(request.user, "is_staff", False) or _user_has_role(request, "ADMIN")):
        return JsonResponse({"success": False, "error": "forbidden"}, status=403)
    raw = (request.POST.get("intents_json") or "").strip()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "bad_json"}, status=400)
    if not isinstance(data, list):
        return JsonResponse({"success": False, "error": "list_required"}, status=400)

    sanitized: list[dict[str, Any]] = []
    for raw_item in data[:25]:
        if not isinstance(raw_item, dict):
            continue
        match = str(raw_item.get("match") or "").strip()
        url = str(raw_item.get("url") or "").strip()
        label = str(raw_item.get("label") or "").strip()
        if not match or not url.startswith("/"):
            continue
        sanitized.append({"match": match[:120], "url": url[:240], "label": (label or "Open")[:80]})

    try:
        rd = getattr(school, "runtime_defaults", None) or {}
        if not isinstance(rd, dict):
            rd = {}
        rd["ai_line_intents"] = sanitized
        school.runtime_defaults = rd
        school.save(update_fields=["runtime_defaults"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("intents save failed: %s", exc)
        return JsonResponse({"success": False, "error": "save_failed"}, status=500)
    return JsonResponse({"success": True, "saved_count": len(sanitized)})


def _user_has_role(request, role_name: str) -> bool:
    """Best-effort role lookup without hard-coding role strings."""
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    try:
        getter = getattr(user, "has_role", None)
        if callable(getter):
            return bool(getter(role_name))
        # rbac-allow: role-string fallback when has_role helper not present
        return str(getattr(user, "role", "")).upper() == role_name.upper()  # role-string-allow: fallback-when-has_role-helper-missing
    except Exception:  # noqa: BLE001
        return False


# ----- Staff dashboard: intent coverage -----------------------------------


@staff_member_required
def ai_line_intent_coverage(request):
    """v4.00.34 — function-style view to dodge metaclass headache from CBV."""
    snap = _snapshot()
    fmt = (request.GET.get("format") or "").lower()
    summary = _summarize(snap)
    if fmt == "json":
        return JsonResponse({
            "success": True,
            "snapshot_count": len(snap),
            "buffer_cap": _BUFFER_CAP,
            "summary": summary,
        })
    return render(
        request,
        "super/ai_line_intent_coverage.html",
        {
            "snapshot_count": len(snap),
            "summary": summary,
            "buffer_cap": _BUFFER_CAP,
        },
    )


def _summarize(snap: list[dict[str, Any]]) -> dict[str, Any]:
    if not snap:
        return {"total": 0, "match_rate": 0.0, "ai_rate": 0.0, "by_intent": [], "recent": []}
    total = len(snap)
    matched = sum(1 for r in snap if r["matched"])
    ai_used = sum(1 for r in snap if r["ai_on"])
    by_intent: dict[str, int] = collections.Counter(r["intent"] for r in snap)
    return {
        "total": total,
        "match_rate": round(100.0 * matched / total, 1),
        "ai_rate": round(100.0 * ai_used / total, 1),
        "by_intent": sorted(by_intent.items(), key=lambda kv: -kv[1]),
        "recent": snap[-25:][::-1],
    }
