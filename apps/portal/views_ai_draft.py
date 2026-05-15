"""Pass 13.D: AI draft endpoints that the `ai_draft_inline.html` partial POSTs to.

Two surfaces:

  - POST /portal/ai/draft/parent-message/
        body: {intent: "...", existing: "..."}
        -> {draft: "...", provider: "gateway|ollama|rules"}

  - POST /portal/ai/draft/report-card-comment/
        body: {intent: "...", existing: "..."}
        -> {draft: "..."}

Both gated by:
  - login + staff-or-teacher (matches `_can_access_direct_messages` so
    teachers and counselors can both use the compose surface)
  - `apps.billing.entitlements.can(school, "AI_TEACHER_COMMS")` for the first;
    `"AI_REPORT_CARD"` for the second.

Failures fail closed: returns {error: "..."} with the right status so the UI
shows the canned message; never raises.
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST

from apps.accounts.models import User

logger = logging.getLogger(__name__)


def _school_from_request(request):
    return getattr(request, "school", None)


def _decode_json(request) -> dict:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return {}


def _entitlement_ok(school, capability: str) -> bool:
    try:
        from apps.billing.entitlements import can
    except ImportError:
        return False
    try:
        return bool(can(school, capability))
    except Exception:  # noqa: BLE001
        return False


def _can_draft(user) -> bool:
    """Same gate as `_can_access_direct_messages` in accounts.views — staff,
    teachers, and admin-style roles can use the AI draft tool."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = (getattr(user, "role", "") or "").upper()
    if role in (User.Role.PARENT, User.Role.STUDENT):
        return False
    return bool(user.is_staff or user.is_superuser or role)


@login_required
@require_POST
def ai_draft_parent_message(request):
    """Draft a parent-facing message based on the teacher's intent text."""
    if not _can_draft(request.user):
        return HttpResponseForbidden(
            "You don't have permission to use AI draft."
        )
    school = _school_from_request(request)
    if school is None:
        return JsonResponse({"error": "School context required."}, status=400)
    if not _entitlement_ok(school, "AI_TEACHER_COMMS"):
        return JsonResponse(
            {"error": "AI teacher comms not enabled for this school."},
            status=402,
        )
    payload = _decode_json(request)
    intent = (payload.get("intent") or "").strip()[:500]
    existing = (payload.get("existing") or "").strip()[:2000]
    if not intent:
        return JsonResponse(
            {"error": "Tell us briefly what the message is about (intent)."},
            status=400,
        )
    try:
        from services.teacher_comms import draft_parent_message
    except ImportError:
        return JsonResponse({"error": "Draft service unavailable."}, status=503)
    teacher = getattr(request.user, "teacher_profile", None)
    # `key_facts` is Iterable[str] in the service contract — pass the
    # operator's existing-draft text as one fact when present.
    key_facts: list[str] = []
    if existing:
        key_facts.append(f"Existing draft: {existing}")
    text, meta = draft_parent_message(
        school=school,
        teacher=teacher,
        student=None,
        intent=intent,
        key_facts=key_facts,
    )
    if not text:
        return JsonResponse(
            {"error": meta.get("error") or "No draft returned."}, status=503
        )
    return JsonResponse({"draft": text, "provider": meta.get("provider", "")})


@login_required
@require_POST
def ai_draft_report_card_comment(request):
    """Draft a 40-60 word report-card comment from an evaluation snapshot."""
    if not _can_draft(request.user):
        return HttpResponseForbidden(
            "You don't have permission to use AI draft."
        )
    school = _school_from_request(request)
    if school is None:
        return JsonResponse({"error": "School context required."}, status=400)
    if not _entitlement_ok(school, "AI_REPORT_CARD"):
        return JsonResponse(
            {"error": "AI report-card drafting not enabled for this school."},
            status=402,
        )
    payload = _decode_json(request)
    intent = (payload.get("intent") or "").strip()[:500]
    existing = (payload.get("existing") or "").strip()[:1500]
    if not intent:
        return JsonResponse(
            {"error": "Tell us the comment focus (intent)."}, status=400
        )
    try:
        from services.teacher_comms import draft_report_card_comment
    except ImportError:
        return JsonResponse({"error": "Draft service unavailable."}, status=503)
    teacher = getattr(request.user, "teacher_profile", None)
    evaluations: list[dict] = []
    if existing:
        evaluations.append({"subject": "(existing draft)", "score": "", "trend": existing[:80]})
    text, meta = draft_report_card_comment(
        school=school,
        teacher=teacher,
        student=None,
        term_name=intent[:60],
        evaluations=evaluations,
    )
    if not text:
        return JsonResponse(
            {"error": meta.get("error") or "No draft returned."}, status=503
        )
    return JsonResponse({"draft": text, "provider": meta.get("provider", "")})
