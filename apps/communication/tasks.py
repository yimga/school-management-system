"""
Celery tasks for communication (e.g. Plan XIII: 3 days perfect attendance → Kudos).
§2.4: broad except replaced with typed exception tuples and structured logging.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Count
from django.utils import timezone

from apps.schools.celery_tasks import _run_with_tenant_context

logger = logging.getLogger(__name__)

# §2.4: typed exceptions for narrative creation and outbound send (provider/DB/network)
_COMMUNICATION_TASK_NARRATIVE_ERRORS: tuple[type[BaseException], ...] = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    OSError,
    ConnectionError,
    TimeoutError,
)
try:
    from django.db.utils import DatabaseError, IntegrityError, OperationalError

    _COMMUNICATION_TASK_NARRATIVE_ERRORS = (
        *_COMMUNICATION_TASK_NARRATIVE_ERRORS,
        DatabaseError,
        IntegrityError,
        OperationalError,
    )
except ImportError:
    pass
_COMMUNICATION_TASK_OUTBOUND_SEND_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ConnectionError,
    TimeoutError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
)

PERFECT_ATTENDANCE_3D_EVENT = "perfect_attendance_3d"


def _students_with_three_consecutive_present(school, end_date):
    """Students who have 'present' for (end_date-2, end_date-1, end_date). One row per student/day."""
    from apps.academics.models import Attendance
    from apps.people.models import StudentProfile

    start = end_date - timedelta(days=2)
    # Count distinct dates with present for each student in [start, end_date]; need exactly 3 days
    student_ids = (
        Attendance.objects.filter(  # tenant-isolation-allow: celery-platform-comms-beat-iterates-active-schools
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
    return list(
        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
        StudentProfile.objects.filter(id__in=student_ids).select_related("school")
    )


@shared_task(bind=True, name="communication.kudos_perfect_attendance_3d")
def kudos_perfect_attendance_3d_task(
    self, as_of_date_str: str | None = None, school_id=None
) -> dict:
    """
    Plan XIII: Find students with 3 consecutive days of perfect attendance and create
    AchievementEvent (perfect_attendance_3d) + optional AI narrative draft.
    Run daily (e.g. after attendance is finalized for the previous day).
    """
    as_of = timezone.now().date()
    if as_of_date_str:
        try:
            as_of = timezone.datetime.strptime(as_of_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    def _run_for_school(current_school_id):
        from apps.communication.models import AchievementEvent
        from apps.communication.narrative_feedback import (
            create_achievement_and_narrative,
        )
        from apps.schools.models import School

        school = School.objects.filter(id=current_school_id, is_active=True).first()
        if not school:
            return {
                "created": 0,
                "skipped": 0,
                "school_id": str(current_school_id),
                "status": "missing_school",
            }

        created = 0
        skipped = 0
        for student in _students_with_three_consecutive_present(school, as_of):
            # Avoid duplicate: already have event for this 3-day window (end_date=as_of)
            exists = AchievementEvent.objects.filter(  # tenant-isolation-allow: celery-platform-comms-beat-iterates-active-schools
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
            except _COMMUNICATION_TASK_NARRATIVE_ERRORS as e:
                from apps.platform_runtime.structured_logging import (
                    log_exception_with_context,
                )

                log_exception_with_context(
                    "communication.tasks.kudos_perfect_attendance_3d: skip student (narrative/create)",
                    school_id=getattr(school, "id", None),
                    extra={
                        "student_id": getattr(student, "id", None),
                        "event_type": PERFECT_ATTENDANCE_3D_EVENT,
                        "error": str(e),
                    },
                )
                skipped += 1
        logger.info(
            "kudos_perfect_attendance_3d: school=%s created=%s skipped=%s",
            school.id,
            created,
            skipped,
        )
        return {
            "created": created,
            "skipped": skipped,
            "school_id": str(school.id),
            "status": "ok",
        }

    if school_id:
        return _run_with_tenant_context(
            school_id=school_id,
            runnable=lambda: _run_for_school(school_id),
        )

    from apps.schools.models import School

    totals = {"created": 0, "skipped": 0, "schools_processed": 0}
    for sid in School.objects.filter(is_active=True).values_list("id", flat=True):  # tenant-isolation-allow: celery-platform-comms-beat-iterates-active-schools
        result = _run_with_tenant_context(
            school_id=sid,
            runnable=lambda sid=sid: _run_for_school(sid),
        )
        totals["created"] += int(result.get("created", 0))
        totals["skipped"] += int(result.get("skipped", 0))
        totals["schools_processed"] += 1
    logger.info(
        "kudos_perfect_attendance_3d: schools=%s created=%s skipped=%s",
        totals["schools_processed"],
        totals["created"],
        totals["skipped"],
    )
    return totals


@shared_task(bind=True, name="communication.process_outbound_message_queue")
def process_outbound_message_queue(self, school_id=None, limit=50) -> dict:
    """
    Plan VI: Process pending OutboundMessageQueue rows; send via WhatsApp/Push.
    Configure WhatsApp/Push in API Center (ServiceIntegration: whatsapp, push).
    Tier 4: celery_task_* via global Celery signals.
    """

    def _process_for_school(current_school_id):
        from datetime import timedelta

        from apps.communication.models import OutboundMessageQueue
        from apps.communication.channels import send_whatsapp, send_push

        # Recover rows stuck in "processing" (a worker died mid-send) by
        # returning them to the retry pool after a grace window.
        stale_before = timezone.now() - timedelta(minutes=15)
        OutboundMessageQueue.objects.filter(  # tenant-isolation-allow: celery-platform-comms-beat-stale-claim-recovery
            status="processing",
            school_id=current_school_id,
            updated_at__lt=stale_before,
        ).update(status="retrying")

        # Atomic claim (audit P2 — concurrent beats/workers double-sent). Pick
        # candidate ids, then flip them to "processing" with a status-guarded UPDATE:
        # only ONE runner's UPDATE matches each row (the others see it already-processing
        # → 0 rows). Works on SQLite + Postgres without select_for_update/skip_locked.
        candidate_ids = list(
            OutboundMessageQueue.objects.filter(  # tenant-isolation-allow: celery-platform-comms-beat-iterates-active-schools
                status__in=("pending", "retrying"),
                school_id=current_school_id,
            )
            .order_by("created_at")
            .values_list("id", flat=True)[:limit]
        )
        if not candidate_ids:
            return {"sent": 0, "failed": 0, "processed": 0, "school_id": str(current_school_id)}
        # Stamp the claim with a per-run marker (its exact claim time) and re-select the
        # work set by that SAME stamp — NOT by the shared "processing" status. Two
        # concurrent runners (beat + the periodic-registry cron, or the drain command
        # beside a worker) each read a distinct now(); the status-guard means only ONE
        # flips a given row, so only its own stamp matches on re-select → the other runner
        # picks up ZERO of those rows. Re-selecting by status alone (the previous code)
        # would let BOTH runners send the same row — an unconditional double-send for
        # WhatsApp/Push, which carry no idempotency key. A bulk .update() bypasses the
        # field's auto_now, so the stamp is explicit (and the stale-claim recovery above
        # keys off the same updated_at).
        claim_stamp = timezone.now()
        OutboundMessageQueue.objects.filter(  # tenant-isolation-allow: ids already school-scoped by the candidate query above
            id__in=candidate_ids, status__in=("pending", "retrying"),
        ).update(status="processing", updated_at=claim_stamp)
        items = list(
            OutboundMessageQueue.objects.filter(  # tenant-isolation-allow: ids already school-scoped by the candidate query above
                id__in=candidate_ids, status="processing", updated_at=claim_stamp
            )
            .select_related("school")
            .order_by("created_at")
        )
        sent = failed = 0
        max_retries = 3
        for item in items:
            school = item.school
            if not school:
                item.status = "failed"
                item.error_message = "Missing school context for outbound message."
                item.save(update_fields=["status", "error_message"])
                failed += 1
                continue
            try:
                if item.channel == OutboundMessageQueue.Channel.WHATSAPP:
                    ok = send_whatsapp(
                        school, item.recipient_identifier, body=item.body
                    )
                elif item.channel == OutboundMessageQueue.Channel.SMS:
                    from apps.communication.notification_service import send_sms

                    ok = send_sms(
                        item.recipient_identifier,
                        item.body,
                        school=school,
                        idempotency_key=item.idempotency_key or f"outbound-{item.id}",
                        # We ARE the drainer — a failure here must NOT re-enqueue
                        # a new row (the existing row's retry_count handles retry).
                        queue_on_failure=False,
                    )
                else:
                    ok = send_push(
                        school, item.recipient_identifier, title="", body=item.body
                    )
                if ok:
                    item.status = "sent"
                    item.sent_at = timezone.now()
                    item.save(update_fields=["status", "sent_at"])
                    sent += 1
                else:
                    item.retry_count = (item.retry_count or 0) + 1
                    if item.retry_count >= max_retries:
                        item.status = "failed"
                        item.error_message = (
                            "Provider returned false or no integration (max retries)"
                        )
                    else:
                        item.status = "retrying"
                        item.error_message = "Provider returned false or no integration"
                    item.save(update_fields=["status", "error_message", "retry_count"])
                    failed += 1
            except _COMMUNICATION_TASK_OUTBOUND_SEND_ERRORS as e:
                item.retry_count = (item.retry_count or 0) + 1
                if item.retry_count >= max_retries:
                    item.status = "failed"
                    item.error_message = str(e)[:500]
                else:
                    item.status = "retrying"
                    item.error_message = str(e)[:500]
                item.save(update_fields=["status", "error_message", "retry_count"])
                failed += 1
                logger.warning(
                    "Outbound queue send failed id=%s (retry %s): %s",
                    item.id,
                    item.retry_count,
                    e,
                )
        return {
            "sent": sent,
            "failed": failed,
            "processed": len(items),
            "school_id": str(current_school_id),
        }

    from apps.communication.models import OutboundMessageQueue

    if school_id:
        return _run_with_tenant_context(
            school_id=school_id,
            runnable=lambda: _process_for_school(school_id),
        )

    orphaned = list(
        OutboundMessageQueue.objects.filter(  # tenant-isolation-allow: celery-platform-comms-beat-iterates-active-schools
            status="pending", school__isnull=True
        ).order_by("created_at")[:limit]
    )
    orphaned_failed = 0
    for item in orphaned:
        item.status = "failed"
        item.error_message = "Missing school context for outbound message."
        item.save(update_fields=["status", "error_message"])
        orphaned_failed += 1

    totals = {
        "sent": 0,
        "failed": orphaned_failed,
        "processed": orphaned_failed,
        "schools_processed": 0,
    }
    # Enumerate schools with ANY non-terminal work — not just "pending". A school whose
    # only rows are stuck in "processing" (a dead worker) or "retrying" (a prior failed
    # send, no newer message) would otherwise never be passed to _process_for_school, so
    # its stale-claim recovery and retry-drain would never run — the dead-drainer bug one
    # level up.
    school_ids = list(
        OutboundMessageQueue.objects.filter(  # tenant-isolation-allow: celery-platform-comms-beat-iterates-active-schools
            status__in=("pending", "retrying", "processing"), school__isnull=False
        )
        .values_list("school_id", flat=True)
        .distinct()
    )
    for sid in school_ids:
        result = _run_with_tenant_context(
            school_id=sid,
            runnable=lambda sid=sid: _process_for_school(sid),
        )
        totals["sent"] += int(result.get("sent", 0))
        totals["failed"] += int(result.get("failed", 0))
        totals["processed"] += int(result.get("processed", 0))
        totals["schools_processed"] += 1
    return totals
