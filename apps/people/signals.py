"""
Signal handlers for people models.
§2.4: Typed exception tuples and log_exception_with_context for event/leadership/AccessRequest paths.
"""

import logging

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError, IntegrityError, OperationalError, ProgrammingError
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver

from apps.communication.models import MessageThread
from apps.people.models import (
    TeacherProfile,
    StudentGuardian,
    StudentProfile,
    TeacherAttendance,
)
from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

# §2.4: Typed tuples for signal/event emission and query paths (no broad except).
_SIGNAL_EMIT_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    ObjectDoesNotExist,
    KeyError,
    DatabaseError,
)
_LEADERSHIP_QUERY_ERRORS = (
    ObjectDoesNotExist,
    DatabaseError,
    OperationalError,
    ProgrammingError,
    AttributeError,
    TypeError,
)
_ACCESS_REQUEST_CREATE_ERRORS = (
    IntegrityError,
    ValidationError,
    ObjectDoesNotExist,
    DatabaseError,
    ValueError,
    TypeError,
    KeyError,
)


@receiver(post_save, sender=TeacherAttendance)
def emit_attendance_recorded_teacher(sender, instance, created, **kwargs):
    """Emit domain event when teacher attendance is recorded (non-negotiable)."""
    if not created:
        return
    try:
        from apps.events.services import emit_event

        school_id = getattr(instance.teacher, "school_id", None)
        emit_event(
            "attendance.recorded",
            {
                "teacher_attendance_id": str(instance.id),
                "teacher_id": str(instance.teacher_id),
                "date": str(instance.date),
                "status": getattr(instance, "status", "") or "",
                "school_id": str(school_id) if school_id else None,
            },
            school_id=school_id,
        )
    except _SIGNAL_EMIT_ERRORS as e:
        log_exception_with_context(
            "emit attendance.recorded (teacher) skipped",
            school_id=getattr(instance.teacher, "school_id", None),
            extra={"teacher_attendance_id": instance.id},
        )
        logger.debug("emit attendance.recorded (teacher) skipped: %s", e)


@receiver(post_save, sender=StudentProfile)
def emit_student_created_event(sender, instance, created, **kwargs):
    """Emit domain event when a student profile is created (service-layer contract). Path-to-10: also emit platform event catalog."""
    if not created:
        return
    school_id = getattr(instance, "school_id", None)
    try:
        from apps.events.services import emit_event

        emit_event(
            "student.created",
            {
                "student_id": str(instance.id),
                "admission_number": getattr(instance, "admission_number", "") or "",
                "school_id": str(school_id) if school_id else None,
            },
            school_id=school_id,
        )
    except _SIGNAL_EMIT_ERRORS as e:
        log_exception_with_context(
            "emit student.created skipped",
            school_id=school_id,
            extra={"student_id": instance.id},
        )
        logger.debug("emit student.created skipped: %s", e)
    try:
        from apps.platform_runtime.event_bus import publish_event

        tid = str(school_id) if school_id else ""
        publish_event(
            "student_created",
            {
                "student_id": instance.id,
                "school_id": school_id,
                "source": "people.signals",
            },
            tenant_id=tid or None,
            school_id=school_id,
            idempotency_key=f"student_created:{instance.id}",
        )
    except _SIGNAL_EMIT_ERRORS as e:
        log_exception_with_context(
            "publish_event student_created skipped",
            school_id=school_id,
            extra={"student_id": instance.id},
        )
        logger.debug("publish_event student_created skipped: %s", e)


@receiver(post_save, sender=StudentProfile)
def emit_student_updated_event(sender, instance, created, **kwargs):
    if created:
        return
    school_id = getattr(instance, "school_id", None)
    try:
        from apps.events.services import emit_event

        emit_event(
            "student.updated",
            {
                "student_id": str(instance.id),
                "school_id": str(school_id) if school_id else None,
            },
            school_id=school_id,
        )
    except _SIGNAL_EMIT_ERRORS as e:
        log_exception_with_context(
            "emit student.updated skipped",
            school_id=school_id,
            extra={"student_id": instance.id},
        )
        logger.debug("emit student.updated skipped: %s", e)


@receiver(post_save, sender=StudentGuardian)
def sync_student_parent_phone_from_guardian(sender, instance, **kwargs):
    """
    One-way sync: when a guardian has phone and the student's parent_phone is empty,
    set student.parent_phone so fallback contact (StudentProfile.parent_phone) stays in sync.
    See docs/archive/legacy_2026_05_14/DATA_PARENT_CONTACT.md.
    """
    if (
        instance.phone
        and instance.student_id
        and not (instance.student.parent_phone or "").strip()
    ):
        instance.student.parent_phone = instance.phone
        instance.student.save(update_fields=["parent_phone"])


@receiver(post_save, sender=TeacherProfile)
def award_onboarding_staff_badge(sender, instance, created, **kwargs):
    """Phase 3: Award 'Active Member' staff badge when a teacher profile is first created."""
    if created and instance.user_id:
        from apps.people.badge_services import create_staff_badge_for_onboarding

        create_staff_badge_for_onboarding(instance)


@receiver(post_save, sender=TeacherProfile)
def sync_teacher_department_thread(sender, instance, created, **kwargs):
    """
    Auto-add teacher to department thread when department is set or updated.
    Creates department thread if it doesn't exist.
    """
    if instance.department and instance.user:
        thread, thread_created = MessageThread.objects.get_or_create(
            scope=MessageThread.Scope.DEPARTMENT,
            department=instance.department,
            defaults={
                "title": f"{instance.department.name} Department",
                "description": f"Group chat for {instance.department.name} department members",
                "created_by": instance.user,
            },
        )
        # Add teacher to thread if not already a member
        if instance.user not in thread.members.all():
            thread.members.add(instance.user)

        # Remove from old department thread if department changed
        if not created and "department" in kwargs.get("update_fields", []):
            # Get old department from previous state (if available)
            # For now, we'll just ensure they're in the current department thread
            pass


def _get_school_leadership_for_assignment(school):
    """Return a user to assign (e.g. Principal/Leadership/Admin) for the school, or None."""
    if not school:
        return None
    try:
        from apps.schools.models import SchoolMembership

        membership = (
            SchoolMembership.objects.filter(school=school)
            .filter(role__in=["LEADERSHIP", "ADMIN", "PRINCIPAL", "IT_ADMIN"])
            .select_related("user")
            .first()
        )
        return membership.user if membership and membership.user_id else None
    except _LEADERSHIP_QUERY_ERRORS:
        return None


@receiver(m2m_changed, sender=StudentProfile.tags.through)
def on_student_critical_tag_added(sender, instance, action, pk_set, **kwargs):
    """
    When a critical InformationTag is added to a student: log, create an AccessRequest
    (OTHER) for the support/dispute workflow, and assign to school leadership if available.
    """
    if action != "post_add" or not pk_set:
        return
    from apps.people.models import InformationTag
    from django.contrib.contenttypes.models import ContentType

    critical_tags = list(
        # tenant-isolation-allow: signal-handler-scoped-via-instance-school-fk
        InformationTag.objects.filter(pk__in=pk_set, is_critical=True).values_list(
            "name", flat=True
        )
    )
    if not critical_tags:
        return
    student = instance
    school = getattr(student, "school", None)
    school_id = getattr(student, "school_id", None)
    tags_str = ", ".join(critical_tags)
    logger.info(
        "Critical tag(s) added to student: student_id=%s school_id=%s tags=%s",
        student.pk,
        school_id,
        critical_tags,
    )
    try:
        from apps.requests.models import AccessRequest

        student_ct = ContentType.objects.get_for_model(StudentProfile)
        title = f"Critical tag(s) added: {tags_str}"
        summary = (
            f"Student {student.get_full_name()} (ID {student.pk}) was assigned critical tag(s): {tags_str}. "
            "Review and take action if needed (e.g. support or dispute workflow)."
        )
        assigned_to = _get_school_leadership_for_assignment(school)
        AccessRequest.objects.create(
            request_type=AccessRequest.RequestType.OTHER,
            status=AccessRequest.Status.PENDING,
            title=title[:200],
            summary=summary,
            details={
                "source": "critical_information_tag",
                "student_id": student.pk,
                "school_id": str(school_id) if school_id else None,
                "tags": critical_tags,
                "student_name": student.get_full_name(),
            },
            requester=None,
            assigned_to=assigned_to,
            target_content_type=student_ct,
            target_object_id=str(student.pk),
        )
        logger.info(
            "Created AccessRequest for critical tag(s); assigned_to=%s", assigned_to
        )
    except _ACCESS_REQUEST_CREATE_ERRORS as e:
        log_exception_with_context(
            "Could not create AccessRequest for critical tag",
            school_id=school_id,
            extra={"student_id": student.pk, "tags": critical_tags},
        )
        logger.warning(
            "Could not create AccessRequest for critical tag: %s", e, exc_info=True
        )


@receiver(post_save, sender=StudentProfile)
def roster_webhook_on_student_save(sender, instance, created, **kwargs):
    """Phase J+: signed roster webhook for district/LMS freshness."""
    try:
        from apps.interop.oneroster.webhook_dispatch import emit_roster_webhook

        school = getattr(instance, "school", None)
        if not school:
            return
        emit_roster_webhook(
            school,
            event="student.created" if created else "student.updated",
            entity="student",
            sourced_id=str(instance.pk),
            payload={
                "student_code": getattr(instance, "student_code", "") or "",
                "classroom_id": str(instance.classroom_id)
                if instance.classroom_id
                else None,
            },
        )
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        logger.debug("roster_webhook student: %s", e)


@receiver(post_save, sender=StudentProfile)
def dispatch_student_automation_workflows(sender, instance, created, **kwargs):
    """School no-code automations: student_updated trigger (non-blocking)."""
    school = getattr(instance, "school", None)
    if not school:
        return
    try:
        from apps.siteconfig.workflow_triggers import dispatch_domain_triggers_safe

        dispatch_domain_triggers_safe(
            school,
            "student_updated",
            {
                "student_id": instance.pk,
                "created": created,
                "student_code": getattr(instance, "student_code", "") or "",
            },
        )
    except ImportError:
        pass


@receiver(post_save, sender=TeacherProfile)
def roster_webhook_on_teacher_save(sender, instance, created, **kwargs):
    try:
        from apps.interop.oneroster.webhook_dispatch import emit_roster_webhook

        school = getattr(instance, "school", None)
        if not school:
            return
        emit_roster_webhook(
            school,
            event="teacher.created" if created else "teacher.updated",
            entity="teacher",
            sourced_id=str(instance.pk),
            payload={},
        )
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        logger.debug("roster_webhook teacher: %s", e)
