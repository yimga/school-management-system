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
from django.urls import NoReverseMatch, Resolver404, resolve, reverse
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


def _load_tenant_overrides(request) -> list[dict[str, Any]]:
    """v4.00.32 — pull tenant-defined intent → URL overrides.

    Read from ``school.runtime_defaults['ai_line_intents']`` if present.
    Shape: ``[{"match": "regex", "label": "...", "url": "/..."}, …]``.
    Tenant admins can preset shortcuts like "fees" → /finance/dashboard/
    that beat the generic patterns below.
    """
    if request is None:
        return []
    school = getattr(request, "school", None)
    if school is None:
        return []
    try:
        rd = getattr(school, "runtime_defaults", None) or {}
        if isinstance(rd, dict):
            data = rd.get("ai_line_intents") or []
        else:
            data = getattr(rd, "ai_line_intents", None) or []
    except Exception as exc:  # noqa: BLE001
        logger.debug("tenant override load failed: %s", exc)
        return []
    out: list[dict[str, Any]] = []
    if not isinstance(data, list):
        return []
    for raw in data[:25]:  # cap to avoid runaway lists
        if not isinstance(raw, dict):
            continue
        match = str(raw.get("match") or "").strip()
        url = str(raw.get("url") or "").strip()
        if not match or not url.startswith("/"):
            continue
        out.append({
            "match": match,
            "label": str(raw.get("label") or "Open"),
            "url": url,
        })
    return out


def _interpret(query: str, request: Any | None = None) -> dict[str, Any] | None:
    q = (query or "").strip().lower()
    if not q:
        return None
    # Strip a leading "/" (slash command) but keep the rest interpretable.
    if q.startswith("/"):
        q = q[1:].strip()
    # Tenant-defined overrides win over built-in handlers.
    for ov in _load_tenant_overrides(request):
        try:
            if re.search(ov["match"], q, re.I):
                return {
                    "matched": True,
                    "label": ov["label"],
                    "url": ov["url"],
                    "params": {},
                    "intent": "tenant_override",
                }
        except re.error:
            continue
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


def _llm_fallback(query: str, request: Any) -> dict[str, Any] | None:
    """Last-resort: route the query through the AI gateway.

    Asks the gateway to emit a JSON object `{"url": "/...", "label": "..."}`
    or empty when no navigation answer applies. Returns None on any failure
    (no AI policy, no gateway, parse error) so the caller keeps the
    deterministic "matched: false" contract intact.
    """
    if not query:
        return None
    try:
        from services.ai_copilot_rbac import guard_copilot_invoke
        from services.ai_helpers import invoke_with_request
    except ImportError:
        return None
    prompt = (
        "You are RunMyCampus's navigation copilot. The operator typed the "
        "following query into the command palette of a school-management "
        "system. Resolve it to a single internal navigation URL on this "
        "platform. Respond with ONLY a JSON object of the shape "
        '{"url": "/finance/...", "label": "Outstanding fees"} '
        'or {"url": "", "label": ""} if no navigation answer applies. '
        "Never invent external URLs; only internal paths starting with /. "
        "If the query is conversational or unanswerable, return empty.\n\n"
        f"Query: {query}\n\n"
        "JSON:"
    )
    guard = guard_copilot_invoke(
        request=request,
        task_type="admin_copilot",
        prompt=prompt,
        user_query=query,
        metadata={"surface": "ai_line"},
    )
    if not guard.allowed:
        return None
    try:
        result = invoke_with_request(
            task_type="admin_copilot",
            prompt=guard.prompt,
            request=request,
            user_query=query,
            metadata=guard.metadata,
            require_available=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("ai-line llm fallback failed: %s", exc)
        return None
    if not result:
        return None
    payload, _meta = result if isinstance(result, tuple) else (result, {})
    text = ""
    if isinstance(payload, str):
        text = payload
    elif isinstance(payload, dict):
        text = (
            payload.get("response")
            or payload.get("text")
            or payload.get("content")
            or ""
        )
        if not text and isinstance(payload.get("message"), dict):
            text = payload["message"].get("content", "")
    text = (text or "").strip()
    if not text:
        return None
    # Extract first JSON object from the response.
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    url = (obj.get("url") or "").strip()
    label = (obj.get("label") or "").strip() or "Open"
    if not url or not url.startswith("/"):
        return None
    # The model is asked for a path and will happily produce a plausible one
    # that does not exist — /finance/outstanding-fees/ reads perfectly and is a
    # 404. Starting with "/" only proved it was internal, not that it was real,
    # so the palette would navigate the reader into a dead end that the AI had
    # invented. A generated destination has to survive the URL resolver before
    # anyone is sent to it; the deterministic intents above already reverse
    # theirs, and this is the same standard applied to the fallback.
    #
    # Resolution proves the route EXISTS on this host, not that this reader may
    # use it — the view keeps its own permission check, as it does for any link.
    try:
        resolve(url.split("?")[0], urlconf=getattr(request, "urlconf", None))
    except Resolver404:
        logger.info(
            "ai-line: discarded a generated destination that resolves nowhere: %r",
            url,
        )
        return None
    return {
        "matched": True,
        "label": label,
        "url": url,
        "params": {},
        "intent": "llm_fallback",
    }


@require_http_methods(["GET", "POST"])
@csrf_protect
@login_required
def api_ai_line_interpret(request):
    """POST/GET q=<natural language> → {matched, label, url, params, intent}.

    Always returns 200 with `matched: false` when no deterministic intent
    AND no LLM fallback fires, so callers can keep their AI/free-text
    fallback without parsing HTTP error codes.

    LLM fallback is opt-in per-request via `&ai=1` (default off) so the
    palette doesn't fan out to the gateway on every keystroke.
    """
    try:
        if request.method == "POST" and request.body:
            body = json.loads(request.body)
        else:
            body = request.GET
        query = (body.get("q") or body.get("query") or "").strip()[:500]
        ai_on = str(body.get("ai", "0")).lower() in ("1", "true", "yes")
    except (ValueError, TypeError) as exc:
        logger.debug("ai-line bad body: %s", exc)
        return JsonResponse({"success": False, "error": "bad_request"}, status=400)
    result = _interpret(query, request=request)
    if not result and ai_on:
        result = _llm_fallback(query, request)
    _log_intent_hit(request, query, result, ai_on)
    if not result:
        return JsonResponse({"success": True, "query": query, "matched": False})
    return JsonResponse({"success": True, "query": query, **result})


_ANALYTICS_LOGGER = logging.getLogger("ai_line.analytics")


def _log_intent_hit(request, query: str, result: dict[str, Any] | None, ai_on: bool) -> None:
    """v4.00.33 — structured logger for AI-line query analytics.

    Emits one structured record per call so operators can see which
    intents convert, which queries miss, and what % of misses escalate
    to the LLM fallback. PII-safe: query is truncated to 80 chars; no
    school slug, user id, or other identifying material is logged
    (school_id only, hashed).
    """
    try:
        school = getattr(request, "school", None)
        school_id_hash = ""
        if school is not None:
            sid = getattr(school, "id", None) or getattr(school, "pk", None)
            if sid is not None:
                import hashlib as _hl
                school_id_hash = _hl.sha256(str(sid).encode("utf-8")).hexdigest()[:12]
        _ANALYTICS_LOGGER.info(
            "ai_line_query intent=%s matched=%s ai_on=%s qlen=%d school=%s url=%s",
            (result or {}).get("intent", "none"),
            bool(result),
            ai_on,
            len(query or ""),
            school_id_hash or "-",
            (result or {}).get("url") or "-",
        )
        # Also stash in the in-process ring buffer that powers the
        # /super/ai-line/intent-coverage/ dashboard.
        try:
            from apps.portal.views_ai_line_admin import record_intent_hit

            record_intent_hit(
                intent=(result or {}).get("intent", "none"),
                matched=bool(result),
                ai_on=ai_on,
                qlen=len(query or ""),
                school=school_id_hash or "-",
                url=(result or {}).get("url") or "-",
            )
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("ai-line analytics log failed: %s", exc)
