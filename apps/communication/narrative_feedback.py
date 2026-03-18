"""
AI narrative feedback: create achievement events and optional LLM-generated
parent message (draft); teacher approves before sending.
"""

from django.utils import timezone

from apps.communication.models import AchievementEvent, NarrativeFeedback


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
    text, _ = generate_ai_response(prompt, user_query=user_query)
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


def mark_narrative_sent(narrative: NarrativeFeedback) -> None:
    """Mark narrative as sent (e.g. after email/push delivered)."""
    narrative.status = NarrativeFeedback.Status.SENT
    narrative.sent_at = timezone.now()
    narrative.save(update_fields=["status", "sent_at", "updated_at"])
