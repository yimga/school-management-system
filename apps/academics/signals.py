"""
Signals for academics app: e.g. notify parents when a student is marked absent or when a disciplinary incident is recorded.
Domain events: enrollment.created, attendance.recorded (non-negotiable).
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Attendance, Incident, StudentDegreeEnrollment

logger = logging.getLogger(__name__)


@receiver(post_save, sender=StudentDegreeEnrollment)
def emit_enrollment_created(sender, instance, created, **kwargs):
    """Emit domain event when a degree enrollment is created."""
    if not created:
        return
    try:
        from apps.events.services import emit_event
        school_id = getattr(instance.student, "school_id", None) if instance.student_id else None
        emit_event(
            "enrollment.created",
            {
                "enrollment_id": str(instance.id),
                "student_id": str(instance.student_id),
                "program_id": str(instance.program_id) if instance.program_id else None,
                "school_id": str(school_id) if school_id else None,
            },
            school_id=school_id,
        )
    except Exception as e:
        logger.debug("emit enrollment.created skipped: %s", e)


@receiver(post_save, sender=Attendance)
def emit_attendance_recorded(sender, instance, created, **kwargs):
    """Emit domain event when student attendance is recorded."""
    try:
        from apps.events.services import emit_event
        school_id = getattr(instance.student, "school_id", None) if getattr(instance, "student_id", None) else None
        emit_event(
            "attendance.recorded",
            {
                "attendance_id": str(instance.id),
                "student_id": str(instance.student_id) if getattr(instance, "student_id", None) else None,
                "date": str(instance.date) if getattr(instance, "date", None) else None,
                "status": getattr(instance, "status", "") or "",
                "school_id": str(school_id) if school_id else None,
            },
            school_id=school_id,
        )
    except Exception as e:
        logger.debug("emit attendance.recorded skipped: %s", e)


@receiver(post_save, sender=Attendance)
def on_attendance_saved(sender, instance, created, **kwargs):
    """When attendance is saved with status ABSENT, optionally notify linked guardians."""
    if instance.status != Attendance.Status.ABSENT:
        return
    try:
        from apps.platform_runtime.helpers import get_effective_flags_for_school
        from apps.people.models import StudentGuardian
        from apps.finance.models import Notification as FinanceNotification

        school = getattr(instance.student, "school", None)
        flags = get_effective_flags_for_school(school) or {}
        if not flags.get("notify_parent_on_absence", False):
            return

        student = instance.student
        guardians = StudentGuardian.objects.filter(
            student=student,
            guardian_user__isnull=False,
        ).select_related("guardian_user")

        student_name = student.get_full_name() or f"Student {student.id}"
        msg = f"{student_name} was marked absent on {instance.date}."
        title = "Absence notice"
        try:
            portal_url = "/portal/parent/"
            for g in guardians:
                if g.guardian_user_id:
                    FinanceNotification.objects.create(
                        title=title,
                        message=msg,
                        link=portal_url,
                        severity=FinanceNotification.Severity.WARNING,
                        recipient_id=g.guardian_user_id,
                        created_by_id=None,
                    )
        except Exception:
            pass
    except Exception:
        pass


@receiver(post_save, sender=Incident)
def on_incident_saved(sender, instance, created, **kwargs):
    """When an incident is saved with notify_parent=True and a student, notify linked guardians."""
    if not instance.student_id or not instance.notify_parent:
        return
    try:
        from apps.people.models import StudentGuardian
        from apps.finance.models import Notification as FinanceNotification

        student = instance.student
        guardians = StudentGuardian.objects.filter(
            student=student,
            guardian_user__isnull=False,
        ).select_related("guardian_user")

        student_name = student.get_full_name() or f"Student {student.id}"
        msg = f"Disciplinary incident recorded for {student_name} on {instance.date}: {instance.get_incident_type_display()}."
        if instance.description:
            msg += f" {instance.description[:200]}"
        title = "Disciplinary notice"
        try:
            portal_url = "/portal/parent/"
            for g in guardians:
                if g.guardian_user_id:
                    FinanceNotification.objects.create(
                        title=title,
                        message=msg,
                        link=portal_url,
                        severity=FinanceNotification.Severity.WARNING,
                        recipient_id=g.guardian_user_id,
                        created_by_id=instance.created_by_id,
                    )
        except Exception:
            pass
    except Exception:
        pass
