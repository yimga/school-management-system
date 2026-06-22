"""Pass 13.D: AI draft endpoints that the `ai_draft_inline.html` partial POSTs to.

Two surfaces:

  - POST /portal/ai/draft/parent-message/
        body: {intent: "...", existing: "...", student_id: optional}
        -> {draft: "...", provider: "gateway|ollama|rules"}

  - POST /portal/ai/draft/report-card-comment/
        body: {intent: "...", existing: "...", student_id: optional}
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


def _permission_refusal_response(text: str, meta: dict) -> JsonResponse | None:
    if isinstance(meta, dict) and meta.get("outcome") == "permission_refusal":
        return JsonResponse({"error": text or "Permission denied."}, status=403)
    return None


def _resolve_student(school, payload: dict):
    raw_student_id = payload.get("student_id")
    if raw_student_id in (None, ""):
        return None
    try:
        from apps.people.models import StudentProfile

        return StudentProfile.objects.filter(
            school=school, pk=int(raw_student_id)
        ).first()
    except (TypeError, ValueError):
        return None


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
    student = _resolve_student(school, payload)
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
    key_facts: list[str] = []
    if existing:
        key_facts.append(f"Existing draft: {existing}")
    text, meta = draft_parent_message(
        school=school,
        teacher=teacher,
        student=student,
        intent=intent,
        key_facts=key_facts,
        user=request.user,
    )
    denied = _permission_refusal_response(text, meta)
    if denied:
        return denied
    if not text:
        return JsonResponse(
            {"error": meta.get("error") or "No draft returned."}, status=503
        )
    return JsonResponse({"draft": text, "provider": meta.get("provider", "")})


@login_required
@require_POST
def ai_draft_announcement(request):
    """Draft a school announcement (audit AI roadmap #1). tone ∈ warm/formal/urgent."""
    if not _can_draft(request.user):
        return HttpResponseForbidden("You don't have permission to use AI draft.")
    school = _school_from_request(request)
    if school is None:
        return JsonResponse({"error": "School context required."}, status=400)
    if not _entitlement_ok(school, "AI_TEACHER_COMMS"):
        return JsonResponse({"error": "AI comms not enabled for this school."}, status=402)
    payload = _decode_json(request)
    intent = (payload.get("intent") or "").strip()[:500]
    audience = (payload.get("audience") or "parents").strip()[:40]
    tone = (payload.get("tone") or "warm").strip()[:20]
    facts = [str(f)[:200] for f in (payload.get("key_facts") or []) if str(f).strip()][:10]
    if not intent:
        return JsonResponse({"error": "Tell us what the announcement is about."}, status=400)
    try:
        from services.messaging_ai import draft_announcement
    except ImportError:
        return JsonResponse({"error": "Draft service unavailable."}, status=503)
    text, meta = draft_announcement(
        school=school,
        audience=audience,
        intent=intent,
        key_facts=facts,
        tone=tone,
        user=request.user,
    )
    denied = _permission_refusal_response(text, meta)
    if denied:
        return denied
    if not text:
        return JsonResponse({"error": meta.get("error") or "No draft returned."}, status=503)
    return JsonResponse({"draft": text, "provider": meta.get("provider", "")})


@login_required
@require_POST
def ai_suggest_subject_lines(request):
    """Suggest email subject lines for a body (audit AI roadmap #2)."""
    if not _can_draft(request.user):
        return HttpResponseForbidden("You don't have permission to use AI draft.")
    school = _school_from_request(request)
    if school is None:
        return JsonResponse({"error": "School context required."}, status=400)
    if not _entitlement_ok(school, "AI_TEACHER_COMMS"):
        return JsonResponse({"error": "AI comms not enabled for this school."}, status=402)
    payload = _decode_json(request)
    body = (payload.get("body") or "").strip()[:2000]
    if not body:
        return JsonResponse({"error": "Provide the message body."}, status=400)
    try:
        from services.messaging_ai import suggest_subject_lines
    except ImportError:
        return JsonResponse({"error": "Suggestion service unavailable."}, status=503)
    return JsonResponse({"subjects": suggest_subject_lines(school=school, body_excerpt=body, user=request.user)})


@login_required
@require_POST
def ai_rewrite_plain_language(request):
    """Rewrite a message at a target reading level (audit AI roadmap #3 — equity)."""
    if not _can_draft(request.user):
        return HttpResponseForbidden("You don't have permission to use AI draft.")
    school = _school_from_request(request)
    if school is None:
        return JsonResponse({"error": "School context required."}, status=400)
    if not _entitlement_ok(school, "AI_TEACHER_COMMS"):
        return JsonResponse({"error": "AI comms not enabled for this school."}, status=402)
    payload = _decode_json(request)
    text = (payload.get("text") or "").strip()[:2000]
    reading_level = (payload.get("reading_level") or "grade 6").strip()[:32]
    if not text:
        return JsonResponse({"error": "Provide the text to rewrite."}, status=400)
    try:
        from services.messaging_ai import rewrite_plain_language
    except ImportError:
        return JsonResponse({"error": "Rewrite service unavailable."}, status=503)
    out, meta = rewrite_plain_language(
        school=school, text=text, reading_level=reading_level, user=request.user
    )
    denied = _permission_refusal_response(out, meta)
    if denied:
        return denied
    return JsonResponse({"draft": out, "provider": meta.get("provider", "")})


@login_required
@require_POST
def ai_suggest_replies(request):
    """Suggest staff replies to an inbound parent message (audit AI roadmap #7)."""
    if not _can_draft(request.user):
        return HttpResponseForbidden("You don't have permission to use AI draft.")
    school = _school_from_request(request)
    if school is None:
        return JsonResponse({"error": "School context required."}, status=400)
    if not _entitlement_ok(school, "AI_TEACHER_COMMS"):
        return JsonResponse({"error": "AI comms not enabled for this school."}, status=402)
    payload = _decode_json(request)
    inbound_text = (payload.get("inbound_text") or "").strip()[:1000]
    context = (payload.get("context") or "").strip()[:500]
    if not inbound_text:
        return JsonResponse({"error": "Provide the inbound message."}, status=400)
    try:
        from services.messaging_ai import suggest_replies
    except ImportError:
        return JsonResponse({"error": "Suggestion service unavailable."}, status=503)
    return JsonResponse(
        {"replies": suggest_replies(
            school=school,
            inbound_text=inbound_text,
            context=context,
            user=request.user,
        )}
    )


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
    student = _resolve_student(school, payload)
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
        evaluations.append(
            {"subject": "(existing draft)", "score": "", "trend": existing[:80]}
        )
    text, meta = draft_report_card_comment(
        school=school,
        teacher=teacher,
        student=student,
        term_name=intent[:60],
        evaluations=evaluations,
        user=request.user,
    )
    denied = _permission_refusal_response(text, meta)
    if denied:
        return denied
    if not text:
        return JsonResponse(
            {"error": meta.get("error") or "No draft returned."}, status=503
        )
    return JsonResponse({"draft": text, "provider": meta.get("provider", "")})


@login_required
@require_POST
def ai_draft_lesson_outline(request):
    """Draft a structured lesson-plan outline for the teacher education pack."""
    if not _can_draft(request.user):
        return HttpResponseForbidden(
            "You don't have permission to use AI draft."
        )
    school = _school_from_request(request)
    if school is None:
        return JsonResponse({"error": "School context required."}, status=400)
    if not _entitlement_ok(school, "AI_TEACHER_COMMS"):
        return JsonResponse(
            {"error": "AI teacher tools not enabled for this school."},
            status=402,
        )
    payload = _decode_json(request)
    intent = (payload.get("intent") or "").strip()[:500]
    subject = (payload.get("subject") or "").strip()[:120]
    grade_level = (payload.get("grade_level") or "").strip()[:80]
    raw_objectives = payload.get("objectives")
    objectives: list[str] = []
    if isinstance(raw_objectives, list):
        objectives = [str(o).strip()[:200] for o in raw_objectives if str(o).strip()][:8]
    if not intent:
        return JsonResponse(
            {"error": "Describe the lesson focus (intent)."},
            status=400,
        )
    try:
        from services.teacher_lesson_plan import draft_lesson_plan_outline
    except ImportError:
        return JsonResponse({"error": "Draft service unavailable."}, status=503)
    teacher = getattr(request.user, "teacher_profile", None)
    text, meta = draft_lesson_plan_outline(
        school=school,
        teacher=teacher,
        subject=subject,
        grade_level=grade_level,
        intent=intent,
        objectives=objectives,
        user=request.user,
    )
    denied = _permission_refusal_response(text, meta)
    if denied:
        return denied
    if not text:
        return JsonResponse(
            {"error": meta.get("error") or "No draft returned."}, status=503
        )
    return JsonResponse({"draft": text, "provider": meta.get("provider", "")})


#: Most recent messages pulled into a thread summary (caps the AI prompt size).
_THREAD_SUMMARY_FETCH_LIMIT = 80


def _display(person) -> str:
    if person is None:
        return "Someone"
    try:
        full = (person.get_full_name() or "").strip()
    except Exception:  # noqa: BLE001
        full = ""
    return full or getattr(person, "username", "") or "Someone"


def _collect_thread_for_summary(request, school, scope: str, raw_id):
    """Return ``([(author, text), ...], kind)`` for a thread the caller is in.

    Access-checked + tenant-scoped: group requires membership; direct requires
    the peer to be in the caller's same-school messageable set. Returns
    ``(None, "")`` when the conversation isn't found / not accessible.
    """
    user = request.user
    try:
        obj_id = int(raw_id)
    except (TypeError, ValueError):
        return None, ""

    if scope == "group":
        from apps.communication.models import MessageThread, ThreadMessage

        # tenant-isolation-allow: thread-scoped-to-caller-membership-then-messages
        thread = MessageThread.objects.filter(pk=obj_id, members=user).first()
        if thread is None:
            return None, ""
        # tenant-isolation-allow: messages-scoped-to-callers-own-member-thread
        msgs = (
            ThreadMessage.objects.filter(thread=thread, is_deleted=False)
            .select_related("author")
            .order_by("created_at")[:_THREAD_SUMMARY_FETCH_LIMIT]
        )
        return [(_display(m.author), m.content) for m in msgs], "group conversation"

    if scope == "direct":
        from django.db.models import Q

        from apps.communication.models import Message
        from apps.accounts.views import _direct_message_user_queryset

        other = _direct_message_user_queryset(request).filter(pk=obj_id).first()
        if other is None:
            return None, ""
        # tenant-isolation-allow: messages-scoped-to-the-caller-and-peer-pair
        msgs = (
            Message.objects.filter(
                Q(sender=user, recipient=other) | Q(sender=other, recipient=user),
                is_archived=False,
            )
            .select_related("sender")
            .order_by("created_at")[:_THREAD_SUMMARY_FETCH_LIMIT]
        )
        return [(_display(m.sender), m.body) for m in msgs], "direct conversation"

    return None, ""


@login_required
@require_POST
def ai_summarize_thread(request):
    """Summarize a direct or group thread the caller participates in (IM-8)."""
    if not _can_draft(request.user):
        return HttpResponseForbidden("You don't have permission to use AI assist.")
    school = _school_from_request(request)
    if school is None:
        return JsonResponse({"error": "School context required."}, status=400)
    if not _entitlement_ok(school, "AI_TEACHER_COMMS"):
        return JsonResponse(
            {"error": "AI assist not enabled for this school."}, status=402
        )
    payload = _decode_json(request)
    scope = (payload.get("scope") or "").strip().lower()
    messages, kind = _collect_thread_for_summary(
        request, school, scope, payload.get("id")
    )
    if messages is None:
        return JsonResponse({"error": "Conversation not found."}, status=404)
    if not messages:
        return JsonResponse({"error": "Nothing to summarize yet."}, status=400)
    try:
        from services.messaging_ai import summarize_thread
    except ImportError:
        return JsonResponse({"error": "Service unavailable."}, status=503)
    out, meta = summarize_thread(
        school=school, messages=messages, user=request.user, kind=kind
    )
    denied = _permission_refusal_response(out, meta)
    if denied:
        return denied
    if not out:
        return JsonResponse(
            {"error": meta.get("error") or "No summary returned."}, status=503
        )
    return JsonResponse({"summary": out, "provider": meta.get("provider", "")})
