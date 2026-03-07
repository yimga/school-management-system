"""
Celery tasks for communication (e.g. Plan XIII: 3 days perfect attendance → Kudos).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Count
from django.utils import timezone

logger = logging.getLogger(__name__)

PERFECT_ATTENDANCE_3D_EVENT = "perfect_attendance_3d"


def _students_with_three_consecutive_present(school, end_date):
    """Students who have 'present' for (end_date-2, end_date-1, end_date). One row per student/day."""
    from apps.academics.models import Attendance
    from apps.people.models import StudentProfile

    start = end_date - timedelta(days=2)
    # Count distinct dates with present for each student in [start, end_date]; need exactly 3 days
    student_ids = (
        Attendance.objects.filter(
            school=school,
            date__gte=start,
            date__lte=end_date,
            status=Attendance.Status.PRESENT,
        )
        .values("student_id")
        .annotate(days=Count("date", distinct=True))
        .filter(days=3)
        .values_list("student_id", flat=True)
    )
    return list(StudentProfile.objects.filter(id__in=student_ids).select_related("school"))


@shared_task(bind=True, name="communication.kudos_perfect_attendance_3d")
def kudos_perfect_attendance_3d_task(self, as_of_date_str: str | None = None) -> dict:
    """
    Plan XIII: Find students with 3 consecutive days of perfect attendance and create
    AchievementEvent (perfect_attendance_3d) + optional AI narrative draft.
    Run daily (e.g. after attendance is finalized for the previous day).
    """
    from apps.communication.models import AchievementEvent
    from apps.communication.narrative_feedback import create_achievement_and_narrative
    from apps.schools.models import School

    as_of = timezone.now().date()
    if as_of_date_str:
        try:
            as_of = timezone.datetime.strptime(as_of_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    created = 0
    skipped = 0
    for school in School.objects.filter(is_active=True):
        for student in _students_with_three_consecutive_present(school, as_of):
            # Avoid duplicate: already have event for this 3-day window (end_date=as_of)
            exists = AchievementEvent.objects.filter(
                school=school,
                student=student,
                event_type=PERFECT_ATTENDANCE_3D_EVENT,
                payload__end_date=as_of.isoformat(),
            ).exists()
            if exists:
                skipped += 1
                continue
            try:
                create_achievement_and_narrative(
                    school=school,
                    student=student,
                    event_type=PERFECT_ATTENDANCE_3D_EVENT,
                    payload={"end_date": as_of.isoformat(), "days": 3},
                    generate_ai=True,
                )
                created += 1
            except Exception as e:
                logger.warning("kudos_perfect_attendance_3d: skip student %s: %s", student.id, e)
    logger.info("kudos_perfect_attendance_3d: created=%s skipped=%s", created, skipped)
    return {"created": created, "skipped": skipped}


@shared_task(bind=True, name="communication.process_outbound_message_queue")
def process_outbound_message_queue(self, school_id=None, limit=50) -> dict:
    """
    Plan VI: Process pending OutboundMessageQueue rows; send via WhatsApp/Push.
    Configure WhatsApp/Push in API Center (ServiceIntegration: whatsapp, push).
    """
    from apps.communication.models import OutboundMessageQueue
    from apps.communication.channels import send_whatsapp, send_push
    from apps.schools.models import School

    qs = OutboundMessageQueue.objects.filter(status="pending").select_related("school").order_by("created_at")
    if school_id:
        qs = qs.filter(school_id=school_id)
    items = list(qs[:limit])
    sent = failed = 0
    for item in items:
        school = item.school
        if not school:
            school = School.objects.filter(is_active=True).first()
        try:
            if item.channel == OutboundMessageQueue.Channel.WHATSAPP:
                ok = send_whatsapp(school, item.recipient_identifier, body=item.body)
            else:
                ok = send_push(school, item.recipient_identifier, title="", body=item.body)
            if ok:
                item.status = "sent"
                item.sent_at = timezone.now()
                item.save(update_fields=["status", "sent_at"])
                sent += 1
            else:
                item.status = "failed"
                item.error_message = "Provider returned false or no integration"
                item.save(update_fields=["status", "error_message"])
                failed += 1
        except Exception as e:
            item.status = "failed"
            item.error_message = str(e)[:500]
            item.save(update_fields=["status", "error_message"])
            failed += 1
            logger.warning("Outbound queue send failed id=%s: %s", item.id, e)
    return {"sent": sent, "failed": failed, "processed": len(items)}
