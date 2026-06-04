"""
Celery tasks for analytics (deadline reminders, etc.).
§2.4: Typed exception tuples and log_exception_with_context for deadline reminder and run paths.
Run via: send_deadline_reminders_task.delay(days_str="7,3,1,0.5", dry_run=False)
Or synchronously from management command when no broker: task.apply(kwargs={...})
"""

from __future__ import annotations

import logging
from datetime import timedelta
from smtplib import SMTPException

from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError, IntegrityError
from django.db.models import Q
from django.utils import timezone

from apps.academics.models import SubjectAssignment
from apps.automation.models import AutomationExecutionLog
from apps.automation.helpers import get_cached_site_settings
from apps.evals.models import TeacherAssignment
from apps.evals.notifications import NotificationService
from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.schools.celery_tasks import _run_with_tenant_context

logger = logging.getLogger(__name__)

# §2.4: Typed tuples for deadline reminder and task run (no broad except).
_ANALYTICS_DEADLINE_EMAIL_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
    SMTPException,
    UnicodeError,
    AttributeError,
    TypeError,
)
_ANALYTICS_DEADLINE_SMS_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
    ValueError,
    TypeError,
    AttributeError,
    KeyError,
)
_ANALYTICS_DEADLINE_RUN_ERRORS = (
    DatabaseError,
    IntegrityError,
    ValidationError,
    ValueError,
    TypeError,
    AttributeError,
    ObjectDoesNotExist,
    KeyError,
)


def run_deadline_reminders(
    days_str: str = "7,3,1,0.5", dry_run: bool = False, school=None
) -> dict:
    """
    Send grading deadline reminders to teachers. Returns summary for logging/CLI.
    """
    try:
        reminder_days = [float(d.strip()) for d in days_str.split(",")]
    except ValueError:
        return {
            "sent": 0,
            "errors": 0,
            "dry_run": dry_run,
            "error": "Invalid days format",
        }

    site_settings = get_cached_site_settings(school=school)
    notification_service = NotificationService()
    today = timezone.now().date()
    teachers_notified = set()
    reminder_count = 0
    error_count = 0

    for days_threshold in reminder_days:
        target_date = today + timedelta(days=days_threshold)
        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
        subject_assignments = SubjectAssignment.objects.filter(
            grading_deadline_at__isnull=False,
            grading_deadline_at__date=target_date,
        ).select_related("academic_year", "term", "classroom", "subject")

        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
        for sa in subject_assignments:
            teacher_assignments = TeacherAssignment.objects.filter(
                subject_assignment=sa
            ).select_related("teacher", "teacher__user")
            for ta in teacher_assignments:
                teacher = ta.teacher
                teacher_key = (teacher.id, days_threshold, sa.id)
                if teacher_key in teachers_notified:
                    continue
                teachers_notified.add(teacher_key)

                subject_name = sa.subject.name
                classroom_name = sa.classroom.name
                deadline_date = sa.grading_deadline_at.strftime("%B %d, %Y")

                if dry_run:
                    logger.info(
                        "[DRY-RUN] Would send reminder to %s (%s in %s, due %s)",
                        ta.teacher.user.email,
                        subject_name,
                        classroom_name,
                        deadline_date,
                    )
                    reminder_count += 1
                    continue

                try:
                    notification_service.send_deadline_reminder_email(
                        teacher=teacher,
                        deadline_at=sa.grading_deadline_at,
                        subject_count=1,
                    )
                    reminder_count += 1
                    logger.info("Sent deadline reminder to %s", teacher.user.email)
                except _ANALYTICS_DEADLINE_EMAIL_ERRORS as e:
                    error_count += 1
                    log_exception_with_context(
                        "Failed to send deadline reminder email",
                        school_id=getattr(sa, "school_id", None)
                        or (getattr(school, "id", None) if school else None),
                        extra={
                            "teacher_email": getattr(teacher.user, "email", ""),
                            "subject_assignment_id": sa.id,
                        },
                    )
                    logger.exception(
                        "Failed to send reminder to %s: %s", teacher.user.email, e
                    )

                if (
                    not dry_run
                    and getattr(site_settings, "sms_provider", None)
                    and site_settings.sms_provider != "console"
                ):
                    try:
                        sms_body = (
                            f"Hi {teacher.user.first_name}, your grading deadline for "
                            f"{subject_name} ({classroom_name}) is {deadline_date}. "
                            f"Please submit your marks."
                        )
                        notification_service.send_sms(
                            phone_number=getattr(teacher.user, "phone_number", "")
                            or "",
                            body=sms_body,
                        )
                    except _ANALYTICS_DEADLINE_SMS_ERRORS as e:
                        log_exception_with_context(
                            "Deadline reminder SMS failed",
                            school_id=getattr(sa, "school_id", None)
                            or (getattr(school, "id", None) if school else None),
                            extra={"phone": getattr(teacher.user, "phone_number", "")},
                        )
                        logger.warning(
                            "SMS failed for %s: %s",
                            getattr(teacher.user, "phone_number", ""),
                            e,
                        )

    return {"sent": reminder_count, "errors": error_count, "dry_run": dry_run}


def _deadline_reminder_days_str(*, school=None) -> str:
    """Read reminder days from cached effective tenant site settings (admin “Site settings”, not code)."""
    site = get_cached_site_settings(school=school)
    days = getattr(site, "teacher_deadline_reminder_days", None) or [7, 3, 1, 0.5]
    if isinstance(days, (list, tuple)):
        return ",".join(str(float(d)) for d in days)
    return "7,3,1,0.5"


@shared_task(bind=True, name="analytics.send_deadline_reminders")
def send_deadline_reminders_task(
    self,
    days_str: str | None = None,
    dry_run: bool = False,
    school_id: str | None = None,
) -> dict:
    """Celery task: send grading deadline reminders to teachers. Uses teacher_deadline_reminder_days from cached effective settings when days_str not provided."""

    def _run_for_school(current_school_id: str) -> dict:
        from apps.schools.models import School

        school = School.objects.filter(id=current_school_id).first()
        resolved_days = days_str
        if resolved_days is None or resolved_days == "":
            resolved_days = _deadline_reminder_days_str(school=school)
        execution_log = AutomationExecutionLog.objects.create(
            task_name="analytics.send_deadline_reminders",
            execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN
            if dry_run
            else AutomationExecutionLog.ExecutionType.SCHEDULED,
            status=AutomationExecutionLog.Status.PENDING,
        )
        try:
            result = run_deadline_reminders(
                days_str=resolved_days, dry_run=dry_run, school=school
            )
            sent = result.get("sent", 0)
            errors = result.get("errors", 0)
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                records_processed=sent,
                records_failed=errors,
                summary={
                    "dry_run": dry_run,
                    "days_str": resolved_days,
                    "school_id": str(current_school_id),
                },
            )
            return {**result, "school_id": str(current_school_id)}
        except _ANALYTICS_DEADLINE_RUN_ERRORS as e:
            log_exception_with_context(
                "send_deadline_reminders_task failed for school",
                school_id=current_school_id,
                extra={"days_str": resolved_days, "dry_run": dry_run},
            )
            logger.exception(
                "send_deadline_reminders_task failed for school=%s", current_school_id
            )
            execution_log.mark_completed(
                AutomationExecutionLog.Status.FAILED,
                error_message=str(e),
            )
            raise

    if school_id:
        return _run_with_tenant_context(
            school_id=school_id,
            runnable=lambda: _run_for_school(school_id),
        )

    from apps.schools.models import School

    totals = {"sent": 0, "errors": 0, "dry_run": dry_run, "schools_processed": 0}
    for sid in School.objects.filter(is_active=True).values_list("id", flat=True):  # tenant-isolation-allow: celery-platform-analytics-beat-iterates-active-schools
        result = _run_with_tenant_context(
            school_id=sid,
            runnable=lambda sid=sid: _run_for_school(str(sid)),
        )
        totals["sent"] += int(result.get("sent", 0))
        totals["errors"] += int(result.get("errors", 0))
        totals["schools_processed"] += 1
    return totals


def _write_student_signals_for_school(school, today, last_30):
    """Pipeline: write StudentSignals (e.g. attendance_ratio_30d) for risk scoring (Plan XVIII)."""
    from decimal import Decimal
    from django.db.models import Count
    from apps.analytics.models import StudentSignals
    from apps.people.models import StudentProfile
    from apps.academics.models import Attendance

    written = 0
    for student in StudentProfile.objects.filter(school=school).values_list(
        "id", flat=True
    ):
        att = Attendance.objects.filter(  # tenant-isolation-allow: celery-platform-analytics-beat-iterates-active-schools
            school=school, student_id=student, date__gte=last_30
        ).aggregate(
            total=Count("id"),
            absent=Count("id", filter=Q(status="absent")),
        )
        total = att["total"] or 0
        absent = att["absent"] or 0
        ratio = (float(total - absent) / total) if total else 1.0
        StudentSignals.objects.create(
            school=school,
            student_id=student,
            signal_type=StudentSignals.SignalType.ATTENDANCE_RATIO_30D,
            value=Decimal(str(round(ratio, 4))),
            payload={"total_days": total, "absent": absent},
        )
        written += 1
    return written


@shared_task(bind=True, name="analytics.compute_risk_factors")
def compute_risk_factors_task(self, school_id: str) -> dict:
    """
    Compute at-risk scores (0-100) for all students in a school.
    Writes StudentSignals (attendance_ratio_30d) then creates/updates RiskFactor rows.
    Used by nightly_risk_factors and POST /api/v1/intervention/calculate-risk.
    """

    def _run_for_school(current_school_id: str) -> dict:
        from decimal import Decimal
        from django.utils import timezone
        from django.db.models import Count
        from datetime import timedelta
        from apps.schools.models import School
        from apps.analytics.models import RiskFactor
        from apps.people.models import StudentProfile
        from apps.academics.models import Attendance

        school = School.objects.filter(id=current_school_id).first()
        if not school:
            return {"status": "error", "message": "School not found"}
        today = timezone.now().date()
        last_30 = today - timedelta(days=30)
        signals_written = _write_student_signals_for_school(school, today, last_30)
        students = StudentProfile.objects.filter(school=school).values_list(
            "id", flat=True
        )
        created = 0
        RiskFactor.objects.filter(school=school).delete()
        for sid in students:
            att = Attendance.objects.filter(  # tenant-isolation-allow: celery-platform-analytics-beat-iterates-active-schools
                school=school, student_id=sid, date__gte=last_30
            ).aggregate(
                total=Count("id"),
                absent=Count("id", filter=Q(status="absent")),
            )
            total = att["total"] or 0
            absent = att["absent"] or 0
            if total:
                pct_absent = float(absent) / float(total) * 100
                score = min(100, Decimal(str(round(pct_absent * 0.4 + 20, 2))))
            else:
                score = Decimal("20.00")
            reason = f"Attendance last 30 days: {total - absent}/{total} present"
            RiskFactor.objects.create(
                school=school,
                student_id=sid,
                score=score,
                reason_summary=reason[:500],
            )
            created += 1
        return {
            "status": "ok",
            "school_id": current_school_id,
            "students_updated": created,
            "signals_written": signals_written,
        }

    return _run_with_tenant_context(
        school_id=school_id,
        runnable=lambda: _run_for_school(school_id),
    )


@shared_task(bind=True, name="analytics.nightly_risk_factors")
def nightly_risk_factors_task(self) -> dict:
    """
    Nightly Celery Beat task: compute and write RiskFactor for all active schools.
    Dispatches one compute_risk_factors_task per school.
    """
    from apps.schools.models import School

    schools = School.objects.filter(is_active=True).values_list("id", flat=True)  # tenant-isolation-allow: celery-platform-analytics-beat-iterates-active-schools
    count = 0
    for school_id in schools:
        compute_risk_factors_task.delay(str(school_id))
        count += 1
    logger.info("nightly_risk_factors: dispatched %s schools", count)
    return {"status": "ok", "schools_dispatched": count}
