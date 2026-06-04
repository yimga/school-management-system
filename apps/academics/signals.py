"""
Signals for academics app: e.g. notify parents when a student is marked absent or when a disciplinary incident is recorded.
Domain events: enrollment.created, attendance.recorded (non-negotiable).
§2.4: All broad except replaced with _ACADEMICS_SIGNAL_ERRORS + structured logging.
"""

import logging
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError, IntegrityError
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from kombu.exceptions import OperationalError as KombuOperationalError

from .models import Attendance, Classroom, Incident, StudentDegreeEnrollment

logger = logging.getLogger(__name__)

# §2.4 Typed exceptions for signal handlers (emit_event, get_effective_flags, Notification.create).
# KombuOperationalError/ConnectionError/OSError: on the free tier there is often
# no Celery broker, so a signal that fires .delay()/.apply_async() raises a
# broker-transport error (NOT a DatabaseError). Without catching it here the
# exception escapes the post_save receiver and ROLLS BACK the business write
# (e.g. an attendance save / enrollment). Swallow + log instead.
_ACADEMICS_SIGNAL_ERRORS = (
    KombuOperationalError,
    ConnectionError,
    OSError,
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    DatabaseError,
    IntegrityError,
    ObjectDoesNotExist,
    ValidationError,
)


def _log_signal_failure(message: str, school_id=None, extra=None):
    try:
        from apps.platform_runtime.structured_logging import log_exception_with_context

        log_exception_with_context(message, school_id=school_id, extra=extra or {})
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        logger.debug("%s (school_id=%s): %s", message, school_id, e, exc_info=True)


@receiver(pre_save, sender=StudentDegreeEnrollment)
def live_compliance_enrollment_strict_br05(sender, instance, **kwargs):
    """BR-05 enrollment: block save when region pack violated (live_compliance_enrollment_strict)."""
    try:
        from apps.compliance.enrollment_region_packs import (
            enrollment_compliance_errors,
            should_enforce_enrollment_strict_block,
        )

        if not should_enforce_enrollment_strict_block(instance):
            return
        errs = enrollment_compliance_errors(instance)
        if errs:
            raise ValidationError(errs)
    except ValidationError:
        raise
    except _ACADEMICS_SIGNAL_ERRORS as exc:
        logger.debug("live_compliance_enrollment_strict_br05: %s", exc)


@receiver(post_save, sender=StudentDegreeEnrollment)
def live_compliance_enrollment_audit_br05(sender, instance, **kwargs):
    """BR-05: audit soft violations when live_compliance_enrollment (feature flags)."""
    try:
        school = getattr(getattr(instance, "student", None), "school", None)
        if not school:
            return
        feats = getattr(school, "features", None) or {}
        if not feats.get("live_compliance_enrollment"):
            return
        from apps.compliance.enrollment_region_packs import (
            enrollment_soft_compliance_issues,
            get_resolved_enrollment_pack,
        )

        issues = enrollment_soft_compliance_issues(instance)
        if not issues:
            return
        from apps.platform_runtime.events import emit_platform_event

        pack = get_resolved_enrollment_pack(instance)
        emit_platform_event(
            "live_compliance_enrollment",
            {
                "enrollment_id": str(instance.id),
                "issues": issues,
                "school_id": str(school.id),
                "enrollment_pack_key": pack.get("key"),
            },
            tenant_id=str(school.id),
            school_id=school.id,
        )
    except _ACADEMICS_SIGNAL_ERRORS as exc:
        logger.debug("live_compliance_enrollment_audit_br05: %s", exc)


@receiver(post_save, sender=StudentDegreeEnrollment)
def emit_enrollment_created(sender, instance, created, **kwargs):
    """Emit domain event when a degree enrollment is created."""
    if not created:
        return
    try:
        from apps.events.services import emit_event

        school_id = (
            getattr(instance.student, "school_id", None)
            if instance.student_id
            else None
        )
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
    except _ACADEMICS_SIGNAL_ERRORS as e:
        logger.debug("emit enrollment.created skipped: %s", e)
        _log_signal_failure(
            "academics signal enrollment.created failed",
            school_id=getattr(instance.student, "school_id", None)
            if instance.student_id
            else None,
            extra={"enrollment_id": instance.id},
        )


@receiver(post_save, sender=Attendance)
def conversion_first_action_on_attendance_saved(sender, instance, **kwargs):
    """Explicit completion signal for conversion lock (not URL-derived)."""
    try:
        school = getattr(getattr(instance, "student", None), "school", None)
        if not school:
            return
        from apps.schools.conversion_lock_state import record_conversion_first_action

        record_conversion_first_action(
            school, source="attendance_saved", request=None, user=None
        )
    except _ACADEMICS_SIGNAL_ERRORS as exc:
        logger.debug("conversion_first_action_on_attendance_saved: %s", exc)


@receiver(post_save, sender=Attendance)
def emit_platform_attendance_saved_bus(sender, instance, **kwargs):
    """Publish platform bus event (webhooks + workflows) for each attendance save."""
    try:
        from django.utils import timezone as dj_tz

        from apps.platform_runtime.event_bus import publish_event

        school = getattr(instance, "school", None)
        if school is None:
            classroom = getattr(instance, "classroom", None)
            school = getattr(classroom, "school", None) if classroom else None
        if school is None:
            return
        recorded_at = getattr(instance, "updated_at", None)
        if recorded_at is not None:
            ra = recorded_at.isoformat()
        else:
            ra = dj_tz.now().isoformat()
        payload = {
            "attendance_id": str(instance.pk),
            "student_id": str(instance.student_id) if instance.student_id else None,
            "classroom_id": str(instance.classroom_id)
            if getattr(instance, "classroom_id", None)
            else None,
            "school_id": str(school.pk),
            "tenant_id": str(school.pk),
            "status": getattr(instance, "status", "") or "",
            "date": str(instance.date) if getattr(instance, "date", None) else None,
            "recorded_at": ra,
            "actor_user_id": None,
        }
        idem = (
            f"attendance_saved:{instance.pk}:{ra}"[:120]
            if ra
            else f"attendance_saved:{instance.pk}"[:120]
        )
        publish_event(
            "attendance_saved",
            payload,
            tenant_id=str(school.pk),
            school_id=school.pk,
            idempotency_key=idem,
        )
    except _ACADEMICS_SIGNAL_ERRORS as exc:
        logger.debug("emit_platform_attendance_saved_bus skipped: %s", exc)


@receiver(post_save, sender=Attendance)
def emit_attendance_recorded(sender, instance, created, **kwargs):
    """Emit domain event when student attendance is recorded."""
    try:
        from apps.events.services import emit_event

        school_id = (
            getattr(instance.student, "school_id", None)
            if getattr(instance, "student_id", None)
            else None
        )
        emit_event(
            "attendance.recorded",
            {
                "attendance_id": str(instance.id),
                "student_id": str(instance.student_id)
                if getattr(instance, "student_id", None)
                else None,
                "date": str(instance.date) if getattr(instance, "date", None) else None,
                "status": getattr(instance, "status", "") or "",
                "school_id": str(school_id) if school_id else None,
            },
            school_id=school_id,
        )
    except _ACADEMICS_SIGNAL_ERRORS as e:
        logger.debug("emit attendance.recorded skipped: %s", e)
        _log_signal_failure(
            "academics signal attendance.recorded failed",
            school_id=getattr(instance.student, "school_id", None)
            if getattr(instance, "student_id", None)
            else None,
            extra={"attendance_id": instance.id},
        )


@receiver(pre_save, sender=Attendance)
def live_compliance_attendance_strict_br05(sender, instance, **kwargs):
    """BR-05 strict: block save when region pack violated (feature live_compliance_attendance_strict)."""
    try:
        from apps.compliance.attendance_region_packs import (
            attendance_compliance_errors,
            should_enforce_strict_block,
        )

        if not should_enforce_strict_block(instance):
            return
        errs = attendance_compliance_errors(instance)
        if errs:
            raise ValidationError(errs)
    except ValidationError:
        raise
    except _ACADEMICS_SIGNAL_ERRORS as exc:
        logger.debug("live_compliance_attendance_strict_br05: %s", exc)


@receiver(post_save, sender=Attendance)
def live_compliance_attendance_br05(sender, instance, **kwargs):
    """BR-05: optional validate-on-write flags → PlatformEventLog when live_compliance_attendance (feature flags)."""
    try:
        school = getattr(instance.student, "school", None)
        if not school:
            return
        feats = getattr(school, "features", None) or {}
        if not feats.get("live_compliance_attendance"):
            return
        from apps.compliance.attendance_region_packs import get_resolved_attendance_pack

        pack = get_resolved_attendance_pack(instance)
        issues = []
        if (
            instance.status == Attendance.Status.ABSENT
            and not (instance.remarks or "").strip()
        ):
            issues.append("absent_without_remarks")
        if not issues:
            return
        from apps.platform_runtime.events import emit_platform_event

        emit_platform_event(
            "live_compliance_attendance",
            {
                "attendance_id": str(instance.id),
                "issues": issues,
                "school_id": str(school.id),
                "date": str(instance.date),
                "attendance_pack_key": pack.get("key"),
            },
            tenant_id=str(school.id),
            school_id=school.id,
        )
    except _ACADEMICS_SIGNAL_ERRORS as exc:
        logger.debug("live_compliance_attendance_br05: %s", exc)


@receiver(post_save, sender=Attendance)
def ews_recompute_on_attendance_br06(sender, instance, **kwargs):
    """BR-06: async risk recompute when ews_recompute_on_attendance (feature flags)."""
    try:
        school = getattr(instance.student, "school", None)
        if not school:
            return
        feats = getattr(school, "features", None) or {}
        if not feats.get("ews_recompute_on_attendance"):
            return
        from apps.analytics.tasks import compute_risk_factors_task

        compute_risk_factors_task.apply_async(
            kwargs={"school_id": str(school.id)}, countdown=90
        )
    except _ACADEMICS_SIGNAL_ERRORS as exc:
        logger.debug("ews_recompute_on_attendance_br06: %s", exc)


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
        school_id = getattr(school, "id", None) if school else None
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
        except _ACADEMICS_SIGNAL_ERRORS:
            _log_signal_failure(
                "academics on_attendance_saved notify guardians failed",
                school_id=school_id,
                extra={"attendance_id": instance.id},
            )
    except _ACADEMICS_SIGNAL_ERRORS:
        _log_signal_failure(
            "academics on_attendance_saved failed",
            school_id=getattr(getattr(instance.student, "school", None), "id", None)
            if getattr(instance, "student_id", None)
            else None,
            extra={"attendance_id": instance.id},
        )


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
        school_id = (
            getattr(getattr(student, "school", None), "id", None) if student else None
        )
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
        except _ACADEMICS_SIGNAL_ERRORS:
            _log_signal_failure(
                "academics on_incident_saved notify guardians failed",
                school_id=school_id,
                extra={"incident_id": instance.id},
            )
    except _ACADEMICS_SIGNAL_ERRORS:
        _log_signal_failure(
            "academics on_incident_saved failed",
            school_id=getattr(getattr(instance.student, "school", None), "id", None)
            if getattr(instance, "student_id", None)
            else None,
            extra={"incident_id": instance.id},
        )


@receiver(post_save, sender=Attendance)
def dispatch_attendance_marked_workflows(sender, instance, created, **kwargs):
    """School automation: attendance_marked trigger."""
    classroom = getattr(instance, "classroom", None)
    school = getattr(classroom, "school", None) if classroom else None
    if not school:
        return
    try:
        from apps.siteconfig.workflow_triggers import dispatch_domain_triggers_safe

        dispatch_domain_triggers_safe(
            school,
            "attendance_marked",
            {
                "attendance_id": instance.pk,
                "student_id": getattr(instance, "student_id", None),
                "classroom_id": getattr(classroom, "pk", None),
                "date": str(getattr(instance, "date", "")),
                "status": getattr(instance, "status", "") or "",
                "created": created,
            },
        )
    except ImportError:
        pass


@receiver(post_save, sender=Classroom)
def roster_webhook_on_classroom_save(sender, instance, created, **kwargs):
    try:
        from apps.interop.oneroster.webhook_dispatch import emit_roster_webhook

        school = getattr(instance, "school", None)
        if not school:
            return
        emit_roster_webhook(
            school,
            event="class.created" if created else "class.updated",
            entity="class",
            sourced_id=str(instance.pk),
            payload={
                "name": getattr(instance, "name", "") or "",
                "code": getattr(instance, "code", "") or "",
            },
        )
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        logger.debug("roster_webhook class: %s", e)
