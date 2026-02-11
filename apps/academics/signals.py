"""
Signals for academics app: e.g. notify parents when a student is marked absent or when a disciplinary incident is recorded.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Attendance, Incident


@receiver(post_save, sender=Attendance)
def on_attendance_saved(sender, instance, created, **kwargs):
    """When attendance is saved with status ABSENT, optionally notify linked guardians."""
    if instance.status != Attendance.Status.ABSENT:
        return
    try:
        from apps.siteconfig.models import SiteSettings
        from apps.people.models import StudentGuardian
        from apps.finance.models import Notification as FinanceNotification

        site = SiteSettings.get_solo()
        flags = getattr(site, "backend_feature_flags", None) or {}
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
