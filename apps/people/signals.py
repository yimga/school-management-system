"""
Signal handlers for people models.
§2.4: Typed exception tuples and log_exception_with_context for event/leadership/AccessRequest paths.
"""

import logging

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError, IntegrityError, OperationalError, ProgrammingError
from django.db.models.signals import post_save, pre_save, m2m_changed
from django.dispatch import receiver

from apps.communication.models import MessageThread
from apps.people.models import (
    Applicant,
    TeacherProfile,
    TeacherLeaveRequest,
    StudentGuardian,
    StudentProfile,
    TeacherAttendance,
)
from apps.platform_runtime.structured_logging import log_exception_with_context
from kombu.exceptions import OperationalError as KombuOperationalError

logger = logging.getLogger(__name__)

# §2.4: Typed tuples for signal/event emission and query paths (no broad except).
# KombuOperationalError/ConnectionError/OSError: free-tier deploys often have no
# Celery broker, so a signal firing .delay() raises a broker-transport error
# (NOT a DatabaseError). Catch it so it can't roll back the student-create write.
_SIGNAL_EMIT_ERRORS = (
    KombuOperationalError,
    ConnectionError,
    OSError,
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


@receiver(post_save, sender=TeacherAttendance)
def open_substitute_market_on_teacher_absence(sender, instance, created, **kwargs):
    """Metric 12 — ABSENT attendance auto-opens the substitute market + notify."""
    status = getattr(instance, "status", "") or ""
    if status != TeacherAttendance.Status.ABSENT:
        return
    if not created:
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "status" not in update_fields:
            return
    try:
        from apps.schoolops.absence_auto_open import (
            maybe_open_market_for_teacher_absence,
        )

        maybe_open_market_for_teacher_absence(instance)
    except Exception as e:  # noqa: BLE001 — attendance path must stay intact
        logger.debug("substitute absence auto-open skipped: %s", e)


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

        # Remove from old department thread if department changed.
        # post_save passes update_fields=None on a full save, so `.get(k, [])`
        # returns None (the key IS present) — guard with `or []` before membership.
        if not created and "department" in (kwargs.get("update_fields") or []):
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


# ── Admissions decision emails (audit C3) ───────────────────────────────
# Applicants were decided (ACCEPTED / REJECTED) with NO notification. We send
# a decision email whenever the stage transitions into a terminal decision.
# A pre_save captures the prior stage so post_save can detect the transition.

_APPLICANT_DECISION_STAGES = {
    Applicant.Stage.ACCEPTED,
    Applicant.Stage.REJECTED,
}


@receiver(pre_save, sender=Applicant)
def _capture_applicant_prior_stage(sender, instance, **kwargs):
    """Stash the DB stage so post_save can detect a real transition."""
    if not instance.pk:
        instance._prior_stage = None
        return
    try:
        instance._prior_stage = (
            sender.objects.filter(pk=instance.pk)  # tenant-isolation-allow: signal-self-row-lookup-by-pk
            .values_list("stage", flat=True)
            .first()
        )
    except _SIGNAL_EMIT_ERRORS:
        instance._prior_stage = None


@receiver(post_save, sender=Applicant)
def send_applicant_decision_email(sender, instance, created, **kwargs):
    """Email the applicant when their stage transitions to a decision (C3)."""
    new_stage = getattr(instance, "stage", "")
    if new_stage not in _APPLICANT_DECISION_STAGES:
        return
    prior = getattr(instance, "_prior_stage", None)
    # Fire only on a genuine transition into the decision stage (not on
    # unrelated saves of an already-decided applicant).
    if not created and prior == new_stage:
        return
    email = (getattr(instance, "email", "") or "").strip()
    if not email:
        return
    school = getattr(instance, "school", None)
    school_name = getattr(school, "name", "") or "the school"
    first = getattr(instance, "first_name", "") or "Applicant"
    accepted = new_stage == Applicant.Stage.ACCEPTED
    if accepted:
        subject = f"Your application to {school_name} — decision"
        body = (
            f"Dear {first},\n\n"
            f"Congratulations! We are pleased to inform you that your application "
            f"to {school_name} has been accepted. Our admissions team will be in "
            f"touch with the next steps to complete your enrolment.\n\n"
            f"Warm regards,\n{school_name} Admissions"
        )
    else:
        subject = f"Your application to {school_name} — decision"
        body = (
            f"Dear {first},\n\n"
            f"Thank you for your interest in {school_name} and for the time you "
            f"invested in your application. After careful review, we are unable to "
            f"offer a place at this time. We wish you every success.\n\n"
            f"Kind regards,\n{school_name} Admissions"
        )
    try:
        from apps.schoolops.email_delivery import send_transactional

        send_transactional(
            subject=subject,
            body=body,
            to=[email],
            priority="transactional",
            school=school,
            idempotency_key=f"applicant_decision:{instance.pk}:{new_stage}",
        )
    except _SIGNAL_EMIT_ERRORS as e:
        logger.warning(
            "people.applicant_decision_email skipped err=%s", type(e).__name__
        )

    # MED-6: emit the `applicant.admitted` notification on the ACCEPTED transition.
    # The Applicant has no linked User (contact is the `email` field only), so we
    # dispatch with recipient=None over the EMAIL channel and pass the address in
    # context — the router's email transport falls back to context["email"]. Routed
    # via the Phase-3 dispatch_event so the ADMISSIONS preference/category applies.
    # Deferred to on_commit + failure-isolated: notifying must never break the save.
    if accepted:
        _emit_applicant_admitted_notification(email=email, school=school)


def _emit_applicant_admitted_notification(*, email: str, school) -> None:
    """Fan an `applicant.admitted` notification to the applicant (email only).

    PII-safe (logs error *type* only), on_commit-deferred, and broadly wrapped so a
    notification failure can never roll back the admissions write.
    """
    try:
        from django.db import transaction

        context = {
            "title": "Application accepted",
            "message": "Congratulations — your application has been accepted.",
            "email": email,
        }

        def _dispatch() -> None:
            from apps.communication.dispatch import dispatch_event
            from apps.communication.models import NotificationPreference

            try:
                dispatch_event(
                    "applicant.admitted",
                    recipient=None,
                    context=context,
                    school=school,
                    # No User row to consult preferences for → drive the EMAIL
                    # channel explicitly (the only deliverable channel for an
                    # email-only applicant).
                    channels=[NotificationPreference.Channel.EMAIL],
                )
            except Exception as exc:  # noqa: BLE001 — never break on-commit hooks
                logger.warning(
                    "applicant.admitted dispatch failed err=%s", type(exc).__name__
                )

        transaction.on_commit(_dispatch)
    except Exception as exc:  # noqa: BLE001 — notify must never break save()
        logger.warning(
            "applicant.admitted emit failed err=%s", type(exc).__name__
        )


#: In-app/email body for a new pending leave request awaiting the approver's
#: decision (named, not a literal at the dispatch call site).
_LEAVE_PENDING_TITLE = "Leave request awaiting your approval"


@receiver(
    post_save,
    sender=TeacherLeaveRequest,
    dispatch_uid="people_teacher_leave_request_pending_notify",
)
def notify_leave_request_approver(sender, instance, created, **kwargs):  # noqa: ARG001
    """Notify the assigned approver when a pending leave request is created.

    MED-6: a newly-created :class:`TeacherLeaveRequest` should alert the person who
    must act on it. There is no dedicated event key for leave approval, so this
    routes through ``dispatch_event`` on the generic path with an explicit channel
    set (it is an action-needed alert, not a behaviour escalation, so the
    ``discipline.incident`` key would be wrong).

    Fires ONLY when:

    * ``created is True`` — never on a decision/update save (no re-notify);
    * ``status == PENDING`` — only an actionable request;
    * ``approver`` is set — a concrete person to notify.

    Best-effort + on_commit-deferred + PII-safe (logs error *type* only). A
    notification failure can never break the leave-request write.

    Other request/approval models in the codebase that do NOT yet notify their
    approver on create (noted, intentionally not wired here): ``payroll.LeaveRequest``
    (no clean school FK), ``finance.RefundRequest``, ``communication.ContactRequest``,
    ``automation.AutomationApprovalQueue``, ``platform_runtime.ConfigurationChangeRequest``.
    ``evals.GradeApprovalRequest`` already notifies its approvers.
    """
    try:
        if not created:
            return
        if getattr(instance, "status", None) != TeacherLeaveRequest.Status.PENDING:
            return
        approver_id = getattr(instance, "approver_id", None)
        if not approver_id:
            return

        approver = instance.approver
        school = getattr(getattr(instance, "teacher", None), "school", None)

        from django.db import transaction

        context = {
            "title": _LEAVE_PENDING_TITLE,
            "message": "A staff leave request is pending your approval.",
            "link": "",
            "severity": "INFO",
        }

        def _dispatch() -> None:
            from apps.communication.dispatch import dispatch_event
            from apps.communication.models import NotificationPreference

            try:
                dispatch_event(
                    # No dedicated leave/approval event key — use the generic path
                    # with an explicit channel set (in-app + email to the approver).
                    "leave.request.pending",
                    recipient=approver,
                    context=context,
                    school=school,
                    channels=[
                        NotificationPreference.Channel.IN_APP,
                        NotificationPreference.Channel.EMAIL,
                    ],
                )
            except Exception as exc:  # noqa: BLE001 — never break on-commit hooks
                logger.warning(
                    "leave.request.pending dispatch failed err=%s",
                    type(exc).__name__,
                )

        transaction.on_commit(_dispatch)
    except Exception as exc:  # noqa: BLE001 — notify must never break save()
        logger.warning(
            "leave.request.pending notify failed err=%s", type(exc).__name__
        )


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
