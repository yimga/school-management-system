"""
Celery tasks for analytics (deadline reminders, etc.).
Run via: send_deadline_reminders_task.delay(days_str="7,3,1,0.5", dry_run=False)
Or synchronously from management command when no broker: task.apply(kwargs={...})
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.academics.models import SubjectAssignment
from apps.automation.models import AutomationExecutionLog
from apps.evals.models import TeacherAssignment
from apps.evals.notifications import NotificationService
from apps.siteconfig.models import SiteSettings

logger = logging.getLogger(__name__)


def run_deadline_reminders(days_str: str = "7,3,1,0.5", dry_run: bool = False) -> dict:
    """
    Send grading deadline reminders to teachers. Returns summary for logging/CLI.
    """
    try:
        reminder_days = [float(d.strip()) for d in days_str.split(",")]
    except ValueError:
        return {"sent": 0, "errors": 0, "dry_run": dry_run, "error": "Invalid days format"}

    site_settings = SiteSettings.get_solo()
    notification_service = NotificationService()
    today = timezone.now().date()
    teachers_notified = set()
    reminder_count = 0
    error_count = 0

    for days_threshold in reminder_days:
        target_date = today + timedelta(days=days_threshold)
        subject_assignments = SubjectAssignment.objects.filter(
            grading_deadline_at__isnull=False,
            grading_deadline_at__date=target_date,
        ).select_related("academic_year", "term", "classroom", "subject")

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
                except Exception as e:
                    error_count += 1
                    logger.exception("Failed to send reminder to %s: %s", teacher.user.email, e)

                if not dry_run and getattr(site_settings, "sms_provider", None) and site_settings.sms_provider != "console":
                    try:
                        sms_body = (
                            f"Hi {teacher.user.first_name}, your grading deadline for "
                            f"{subject_name} ({classroom_name}) is {deadline_date}. "
                            f"Please submit your marks."
                        )
                        notification_service.send_sms(
                            phone_number=getattr(teacher.user, "phone_number", "") or "",
                            body=sms_body,
                        )
                    except Exception as e:
                        logger.warning("SMS failed for %s: %s", getattr(teacher.user, "phone_number", ""), e)

    return {"sent": reminder_count, "errors": error_count, "dry_run": dry_run}


def _deadline_reminder_days_str() -> str:
    """Read reminder days from SiteSettings (config in Site Settings, not code)."""
    site = SiteSettings.get_solo()
    days = getattr(site, "teacher_deadline_reminder_days", None) or [7, 3, 1, 0.5]
    if isinstance(days, (list, tuple)):
        return ",".join(str(float(d)) for d in days)
    return "7,3,1,0.5"


@shared_task(bind=True, name="analytics.send_deadline_reminders")
def send_deadline_reminders_task(self, days_str: str | None = None, dry_run: bool = False) -> dict:
    """Celery task: send grading deadline reminders to teachers. Uses SiteSettings.teacher_deadline_reminder_days when days_str not provided."""
    if days_str is None or days_str == "":
        days_str = _deadline_reminder_days_str()
    execution_log = AutomationExecutionLog.objects.create(
        task_name="analytics.send_deadline_reminders",
        execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN if dry_run else AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.PENDING,
    )
    try:
        result = run_deadline_reminders(days_str=days_str, dry_run=dry_run)
        sent = result.get("sent", 0)
        errors = result.get("errors", 0)
        execution_log.mark_completed(
            AutomationExecutionLog.Status.SUCCESS,
            records_processed=sent,
            records_failed=errors,
            summary={"dry_run": dry_run, "days_str": days_str},
        )
        return result
    except Exception as e:
        logger.exception("send_deadline_reminders_task failed")
        execution_log.mark_completed(
            AutomationExecutionLog.Status.FAILED,
            error_message=str(e),
        )
        raise
