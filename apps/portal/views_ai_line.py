"""v4.00.30 AI-line natural-language → navigation interpreter.

Lightweight, no-LLM-required interpreter that converts queries like:

  "students who haven't paid term 2"
  "fees outstanding for grade 10"
  "open admissions queue"
  "compose announcement for parents"

into a structured navigation suggestion (URL + label + filter hints) so the
command palette can offer a single-click jump. Falls back to None when no
deterministic match — caller (cmdk) can still surface a free-text "Ask AI"
escape hatch.

Pattern-based on purpose: keeps the round-trip cheap, avoids gateway calls
for trivial intents, and stays predictable in low-connectivity tenants.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import NoReverseMatch, reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


# ---------- Intent patterns ---------------------------------------------------
# Order matters — first match wins. Patterns are deliberately broad (free-form
# NL) and trimmed/normalized before matching.


_TERM_RE = re.compile(r"\bterm\s*([1-4])\b", re.I)
_GRADE_RE = re.compile(r"\bgrade\s*(\d{1,2})\b", re.I)


def _intent_unpaid_students(q: str) -> dict[str, Any] | None:
    if not re.search(r"\b(unpaid|haven'?t paid|not paid|owe|outstanding)\b", q):
        return None
    if "student" not in q and "fee" not in q and "invoice" not in q:
        return None
    term = _TERM_RE.search(q)
    grade = _GRADE_RE.search(q)
    params: dict[str, str] = {"status": "unpaid"}
    if term:
        params["term"] = term.group(1)
    if grade:
        params["grade"] = grade.group(1)
    return {
        "route": "finance:outstanding_fees",
        "label": "Outstanding fees",
        "params": params,
        "fallback_url": "/finance/fees/outstanding/",
    }


def _intent_admissions_queue(q: str) -> dict[str, Any] | None:
    if not re.search(r"\b(admissions?|applicants?|enroll(?:ment)?|intake)\b", q):
        return None
    if not re.search(r"\b(queue|pending|new|inbox|review|open)\b", q):
        return None
    return {
        "route": "admissions:queue",
        "label": "Admissions queue",
        "params": {},
        "fallback_url": "/admissions/queue/",
    }


def _intent_compose_announcement(q: str) -> dict[str, Any] | None:
    if not re.search(r"\b(send|compose|write|announce|broadcast|message|notify)\b", q):
        return None
    if not re.search(r"\b(announcement|message|notice|parents?|teachers?|staff|students?)\b", q):
        return None
    audience = ""
    for who in ("parents", "teachers", "staff", "students"):
        if who in q:
            audience = who
            break
    params = {"audience": audience} if audience else {}
    return {
        "route": "comms:compose",
        "label": "Compose announcement",
        "params": params,
        "fallback_url": "/communications/compose/",
    }


def _intent_attendance_today(q: str) -> dict[str, Any] | None:
    if "attendance" not in q:
        return None
    if not re.search(r"\b(today|now|current)\b", q):
        return None
    return {
        "route": "attendance:today",
        "label": "Today's attendance",
        "params": {},
        "fallback_url": "/attendance/today/",
    }


def _intent_grade_entry(q: str) -> dict[str, Any] | None:
    if not re.search(r"\b(grade|mark)s?\b", q):
        return None
    if not re.search(r"\b(enter|input|bulk|record|post)\b", q):
        return None
    return {
        "route": "evals:bulk_grade_entry",
        "label": "Bulk grade entry",
        "params": {},
        "fallback_url": "/evals/teacher/marks/bulk/",
    }


def _intent_timetable(q: str) -> dict[str, Any] | None:
    if not re.search(r"\b(timetable|schedule|class.*time|roster)\b", q):
        return None
    return {
        "route": "academics:timetable",
        "label": "Timetable",
        "params": {},
        "fallback_url": "/academics/timetable/",
    }


def _intent_report_cards(q: str) -> dict[str, Any] | None:
    if not re.search(r"\b(report card|bulletin|transcript)\b", q):
        return None
    return {
        "route": "evals:report_cards",
        "label": "Report cards",
        "params": {},
        "fallback_url": "/evals/report-cards/",
    }


def _intent_help(q: str) -> dict[str, Any] | None:
    if not re.search(r"\b(help|how do i|how to|support|stuck)\b", q):
        return None
    return {
        "route": "feedback:help_center",
        "label": "Help Center",
        "params": {"q": q},
        "fallback_url": "/help/",
    }


_INTENT_HANDLERS = (
    _intent_unpaid_students,
    _intent_admissions_queue,
    _intent_compose_announcement,
    _intent_attendance_today,
    _intent_grade_entry,
    _intent_timetable,
    _intent_report_cards,
    _intent_help,
)


def _resolve_url(route: str, params: dict[str, str], fallback: str) -> str:
    try:
        base = reverse(route)
    except NoReverseMatch:
        base = fallback
    if not params:
        return base
    encoded = "&".join(f"{k}={v}" for k, v in params.items() if v)
    return f"{base}?{encoded}" if encoded else base


def _interpret(query: str) -> dict[str, Any] | None:
    q = (query or "").strip().lower()
    if not q:
        return None
    # Strip a leading "/" (slash command) but keep the rest interpretable.
    if q.startswith("/"):
        q = q[1:].strip()
    for handler in _INTENT_HANDLERS:
        match = handler(q)
        if match:
            url = _resolve_url(match["route"], match["params"], match["fallback_url"])
            return {
                "matched": True,
                "label": match["label"],
                "url": url,
                "params": match["params"],
                "intent": handler.__name__.replace("_intent_", ""),
            }
    return None


@require_http_methods(["GET", "POST"])
@csrf_protect
@login_required
def api_ai_line_interpret(request):
    """POST/GET q=<natural language> → {matched, label, url, params, intent}.

    Always returns 200 with `matched: false` when no deterministic intent
    fires, so callers can keep their AI/free-text fallback without parsing
    HTTP error codes.
    """
    try:
        if request.method == "POST" and request.body:
            body = json.loads(request.body)
        else:
            body = request.GET
        query = (body.get("q") or body.get("query") or "").strip()[:500]
    except (ValueError, TypeError) as exc:
        logger.debug("ai-line bad body: %s", exc)
        return JsonResponse({"success": False, "error": "bad_request"}, status=400)
    result = _interpret(query)
    if not result:
        return JsonResponse({"success": True, "query": query, "matched": False})
    return JsonResponse({"success": True, "query": query, **result})
