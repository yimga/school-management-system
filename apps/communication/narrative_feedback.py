"""
AI narrative feedback: create achievement events and optional LLM-generated
parent message (draft); teacher approves before sending.
"""

import logging

from django.utils import timezone

from apps.communication.models import AchievementEvent, NarrativeFeedback

logger = logging.getLogger(__name__)


def create_achievement_event(
    school, student, event_type: str, payload: dict | None = None
) -> AchievementEvent:
    """Record an achievement event (e.g. perfect_attendance_3d, grade_improved_math)."""
    return AchievementEvent.objects.create(
        school=school,
        student=student,
        event_type=event_type,
        payload=payload or {},
    )


def generate_narrative_for_achievement(
    achievement_event: AchievementEvent,
    *,
    max_length: int = 280,
) -> NarrativeFeedback | None:
    """
    Use AI to generate a short, warm message for the parent about this achievement.
    Creates a NarrativeFeedback in DRAFT status for teacher approval.
    """
    try:
        from apps.portal.ai_provider import generate_ai_response
        from services.ai_helpers import normalize_gateway_metadata
    except ImportError:
        return None

    event_type = achievement_event.event_type
    payload = achievement_event.payload or {}
    student_name = getattr(
        achievement_event.student, "get_full_name", lambda: "Your child"
    )()
    prompt = (
        f"Generate a single short, warm message (under {max_length} characters) for a parent, "
        f"about this school achievement. Write in second person (e.g. 'Your child...'). "
        f"Achievement type: {event_type}. "
        f"Details: {payload}. "
        f"Student first name only if helpful: {student_name}. "
        f"Output only the message text, no quotes or labels."
    )
    user_query = f"narrative for {event_type}"  # safe, for policy check
    school = achievement_event.school
    school_id = getattr(school, "pk", None) or getattr(school, "id", None)
    country_code = getattr(school, "country_code", None) or getattr(
        getattr(school, "default_region", None),
        "code",
        None,
    )
    text, _ = generate_ai_response(
        prompt,
        user_query=user_query,
        metadata=normalize_gateway_metadata(
            {
                "school": school,
                "school_id": str(school_id) if school_id is not None else None,
                "tenant_id": str(school_id) if school_id is not None else None,
                "country_code": country_code,
                "copilot_rbac_skip": "system-achievement-narrative-draft",
            }
        ),
    )
    if not (text and text.strip()):
        text = f"Good news: {event_type.replace('_', ' ')}."
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."

    return NarrativeFeedback.objects.create(
        school=achievement_event.school,
        student=achievement_event.student,
        achievement_event=achievement_event,
        message_text=text.strip(),
        status=NarrativeFeedback.Status.DRAFT,
    )


def create_achievement_and_narrative(
    school,
    student,
    event_type: str,
    payload: dict | None = None,
    *,
    generate_ai: bool = True,
) -> tuple[AchievementEvent, NarrativeFeedback | None]:
    """
    Create an achievement event and optionally an AI-generated narrative draft.
    Returns (event, narrative_feedback or None).
    """
    event = create_achievement_event(school, student, event_type, payload)
    narrative = None
    if generate_ai:
        narrative = generate_narrative_for_achievement(event)
    return event, narrative


def approve_narrative(narrative: NarrativeFeedback, approved_by) -> None:
    """Mark narrative as approved (teacher approval step)."""
    narrative.status = NarrativeFeedback.Status.APPROVED
    narrative.approved_by = approved_by
    narrative.approved_at = timezone.now()
    narrative.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])


def dispatch_narrative_to_guardians(narrative: NarrativeFeedback) -> int:
    """Deliver an approved kudos narrative to the student's guardians.

    Routes through the shared notification rail (``dispatch_event``) so the parent
    actually receives the message — an email plus the in-app bell — with each
    guardian's notification preferences honoured. Best-effort per guardian: one
    failing send never blocks the others. Returns the number of guardians the
    message was dispatched to (0 when the narrative has no student / no guardians,
    which is logged so a silently undeliverable kudos is visible).
    """
    from apps.communication.dispatch import Channel, dispatch_event
    from apps.finance.models import Notification

    student = getattr(narrative, "student", None)
    if student is None:
        logger.warning("narrative.no_student narrative=%s", getattr(narrative, "pk", None))
        return 0

    from apps.people.models import StudentGuardian

    # tenant-isolation-allow: guardians-resolved-from-the-narrative's-own-student
    links = StudentGuardian.objects.filter(
        student=student, is_active=True
    ).select_related("guardian_user")

    message = (narrative.message_text or "").strip()
    count = 0
    seen: set = set()
    for link in links:
        guardian = getattr(link, "guardian_user", None)
        if guardian is None or guardian.pk in seen:
            continue
        seen.add(guardian.pk)
        dispatch_event(
            "achievement.kudos",
            recipient=guardian,
            school=narrative.school,
            context={
                "title": "A note from school",
                "message": message,
                "severity": Notification.Severity.INFO,
            },
            channels=[Channel.EMAIL, Channel.IN_APP],
        )
        count += 1
    if count == 0:
        logger.warning(
            "narrative.no_guardians narrative=%s student=%s",
            getattr(narrative, "pk", None),
            getattr(student, "pk", None),
        )
    return count


def mark_narrative_sent(narrative: NarrativeFeedback) -> None:
    """Deliver the narrative to the student's guardians, then mark it SENT.

    Before this, the method only flipped the status flag — the parent received
    nothing. It now dispatches through the notification rail (email + in-app
    bell) first, then records the row as SENT. Delivery is best-effort: a
    transport failure is logged but must not strand the row as an unsent draft.
    """
    try:
        dispatch_narrative_to_guardians(narrative)
    except Exception:  # noqa: BLE001 — a delivery failure must not strand the row
        logger.warning(
            "narrative.dispatch_failed narrative=%s",
            getattr(narrative, "pk", None),
            exc_info=True,
        )
    narrative.status = NarrativeFeedback.Status.SENT
    narrative.sent_at = timezone.now()
    narrative.save(update_fields=["status", "sent_at", "updated_at"])
