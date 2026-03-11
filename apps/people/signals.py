"""
Signal handlers for people models.
"""
import logging
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from apps.communication.models import MessageThread
from apps.people.models import TeacherProfile, StudentGuardian, StudentProfile, TeacherAttendance

logger = logging.getLogger(__name__)


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
    except Exception as e:
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
    except Exception as e:
        logger.debug("emit student.created skipped: %s", e)
    try:
        from apps.platform_runtime.events import emit_platform_event
        emit_platform_event(
            "student_created",
            {"student_id": instance.id, "school_id": school_id},
            school_id=school_id,
        )
    except Exception as e:
        logger.debug("emit_platform_event student_created skipped: %s", e)


@receiver(post_save, sender=StudentGuardian)
def sync_student_parent_phone_from_guardian(sender, instance, **kwargs):
    """
    One-way sync: when a guardian has phone and the student's parent_phone is empty,
    set student.parent_phone so fallback contact (StudentProfile.parent_phone) stays in sync.
    See docs/DATA_PARENT_CONTACT.md.
    """
    if instance.phone and instance.student_id and not (instance.student.parent_phone or "").strip():
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
                'title': f"{instance.department.name} Department",
                'description': f"Group chat for {instance.department.name} department members",
                'created_by': instance.user,
            }
        )
        # Add teacher to thread if not already a member
        if instance.user not in thread.members.all():
            thread.members.add(instance.user)
        
        # Remove from old department thread if department changed
        if not created and 'department' in kwargs.get('update_fields', []):
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
    except Exception:
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

    critical_tags = list(InformationTag.objects.filter(pk__in=pk_set, is_critical=True).values_list("name", flat=True))
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
        logger.info("Created AccessRequest for critical tag(s); assigned_to=%s", assigned_to)
    except Exception as e:
        logger.warning("Could not create AccessRequest for critical tag: %s", e, exc_info=True)
