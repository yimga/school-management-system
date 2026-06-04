"""Notification service for SMS, email, digests. Uses unified communication notification service (no direct Twilio/AfricasTalking).
§2.4 Typed exceptions + structured logging for send failure paths (broad_exception_audit; allowlist 0).
"""

import logging
from smtplib import SMTPException
from typing import Any, Dict, List
from urllib.parse import quote_plus

from django.conf import settings
from apps.schoolops.email_compat import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from apps.communication.notification_service import (
    send_email as _send_email,
    send_sms as _send_sms,
)
from apps.platform_runtime.structured_logging import log_exception_with_context

# §2.4: Typed exceptions for email/SMS send failures (broad_exception_audit)
_EVALS_NOTIFICATION_SEND_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
    SMTPException,
    ValueError,
    TypeError,
    AttributeError,
    KeyError,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Handles SMS, Email, digests, and WhatsApp deeplinks."""

    # Simple built-in WhatsApp templates for common flows. Keys are short
    # identifiers that callers can pass to ``send_whatsapp``.
    WHATSAPP_TEMPLATES: Dict[str, str] = {
        "CONTACT_ACK": (
            "Hello {guardian_name}, we received your request #{ticket_id} "
            "and will follow up shortly. You can also check the portal at {portal_link}."
        ),
        "RESULTS_PUBLISHED_PARENT": (
            "Hi {guardian_name}, {student_name}'s {term_name} report is ready. "
            "View it in the parent portal: {portal_link}."
        ),
        "GENERIC": "Hello {guardian_name}, this is a message from the school portal.",
    }

    def __init__(self):
        self.site_settings = (
            settings.SITE_SETTINGS if hasattr(settings, "SITE_SETTINGS") else None
        )

    def send_grade_publication_email(self, student, term, recipient_email):
        """Email when grades published."""
        try:
            context = {
                "student_name": student.get_full_name(),
                "term_name": term.label,
                "academic_year": term.academic_year.name,
                "portal_link": f"{settings.BASE_URL}/portal/parent/results/{student.id}/"
                if hasattr(settings, "BASE_URL")
                else "#",
            }

            html_message = render_to_string("emails/grade_publication.html", context)
            plain_message = render_to_string("emails/grade_publication.txt", context)

            send_mail(
                subject=f"Report Card: {student.get_full_name()} - {term.label}",
                message=plain_message,
                from_email=self.site_settings.email_from_address
                if self.site_settings
                else settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                html_message=html_message,
            )

            logger.info(f"Grade publication email sent to {recipient_email}")
            return True
        except _EVALS_NOTIFICATION_SEND_ERRORS as e:
            school_id = getattr(student, "school_id", None) or getattr(
                getattr(term, "academic_year", None), "school_id", None
            )
            log_exception_with_context(
                "evals send_grade_publication_email failed",
                school_id=school_id,
                exc_info=True,
                extra={"recipient": recipient_email, "error": str(e)},
            )
            return False

    def send_grade_publication_sms(self, guardian, student, term):
        """SMS with link when grades published."""
        try:
            portal_link = (
                f"{settings.BASE_URL}/portal/results/{student.id}/"
                if hasattr(settings, "BASE_URL")
                else "portal"
            )
            message = (
                f"Hi {guardian.guardian_user.first_name}, "
                f"{student.get_full_name()}'s {term.label} report is ready. "
                f"View: {portal_link}"
            )
            return _send_sms(guardian.phone, message, site_settings=self.site_settings)
        except _EVALS_NOTIFICATION_SEND_ERRORS as e:
            school_id = getattr(student, "school_id", None) or getattr(
                getattr(term, "academic_year", None), "school_id", None
            )
            log_exception_with_context(
                "evals send_grade_publication_sms failed",
                school_id=school_id,
                exc_info=True,
                extra={
                    "recipient_phone": getattr(guardian, "phone", None),
                    "error": str(e),
                },
            )
            return False

    def send_deadline_reminder_email(self, teacher, deadline_at, subject_count):
        """Email reminder to teacher. teacher is TeacherProfile (has .user)."""
        try:
            days_left = (deadline_at - timezone.now()).days
            user = getattr(teacher, "user", teacher)
            teacher_name = (
                (getattr(user, "get_full_name", None) and user.get_full_name())
                or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
                or getattr(user, "username", "")
            )
            context = {
                "teacher_name": teacher_name,
                "deadline_at": deadline_at,
                "days_left": days_left,
                "subject_count": subject_count,
                "entry_link": f"{settings.BASE_URL}/evals/teacher/marks/entry/"
                if hasattr(settings, "BASE_URL")
                else "#",
            }

            html_message = render_to_string("emails/deadline_reminder.html", context)
            plain_message = render_to_string("emails/deadline_reminder.txt", context)

            send_mail(
                subject=f"Grading Deadline Reminder: {deadline_at.strftime('%B %d')}",
                message=plain_message,
                from_email=self.site_settings.email_from_address
                if self.site_settings
                else settings.DEFAULT_FROM_EMAIL,
                recipient_list=[teacher.user.email],
                html_message=html_message,
            )

            logger.info(f"Deadline reminder email sent to {teacher.user.email}")
            return True
        except _EVALS_NOTIFICATION_SEND_ERRORS as e:
            log_exception_with_context(
                "evals send_deadline_reminder_email failed",
                extra={
                    "recipient": getattr(teacher.user, "email", None),
                    "error": str(e),
                },
            )
            return False

    def send_sms(
        self, phone_number: str, message: str, *, fallback_email: str | None = None
    ) -> bool:
        """Send SMS via unified notification service (Twilio/AfricasTalking adapters); optional fallback to email."""
        return _send_sms(
            phone_number,
            message,
            site_settings=self.site_settings,
            fallback_email=fallback_email,
        )

    def send_notification(
        self,
        user: Any,
        title: str,
        message: str,
        *,
        channels: List[str] | None = None,
    ) -> bool:
        """Send notification to user via requested channels (email, sms). Uses unified notification service."""
        channels = channels or ["email"]
        ok = False
        email = getattr(user, "email", None) if user else None
        if email and isinstance(email, str) and email.strip() and "email" in channels:
            ok = (
                _send_email(
                    [email],
                    subject=title,
                    body=message,
                    site_settings=self.site_settings,
                )
                or ok
            )
        if "sms" in channels and user:
            phone = getattr(user, "phone", None) or getattr(user, "mobile", None)
            if phone and isinstance(phone, str) and phone.strip():
                ok = (
                    _send_sms(
                        phone,
                        message=f"{title}\n\n{message}" if title else message,
                        site_settings=self.site_settings,
                        fallback_email=email,
                    )
                    or ok
                )
        return ok

    # ------------------------------------------------------------------
    # WhatsApp helpers (deeplink generation only for now)
    # ------------------------------------------------------------------

    def _resolve_phone_for_whatsapp(self, user_or_phone: Any) -> str | None:
        """Best-effort phone resolver for WhatsApp.

        Accepts either a raw phone string or objects that commonly appear in
        this codebase (guardian profile, user, tickets with contact_whatsapp, etc.).
        """

        if isinstance(user_or_phone, str):
            return user_or_phone

        for attr in ("whatsapp", "phone", "mobile", "contact_whatsapp"):
            value = getattr(user_or_phone, attr, None)
            if value:
                return str(value)

        guardian_user = getattr(user_or_phone, "guardian_user", None)
        if guardian_user is not None:
            for attr in ("whatsapp", "phone", "mobile"):
                value = getattr(guardian_user, attr, None)
                if value:
                    return str(value)

        return None

    def _build_whatsapp_url(self, phone: str, message: str) -> str:
        base_url = getattr(settings, "WHATSAPP_BASE_URL", "https://wa.me")
        return f"{base_url.rstrip('/')}/{quote_plus(phone)}?text={quote_plus(message)}"

    def send_whatsapp(
        self, user_or_phone: Any, template_key: str, context: Dict[str, Any]
    ) -> str:
        """Generate a WhatsApp deeplink for the given template.

        Returns the `wa.me` URL so callers can surface it in templates or
        redirect links. All actual sending happens on the user's device.
        """

        phone = self._resolve_phone_for_whatsapp(user_or_phone)
        if not phone:
            logger.info(
                "Skipping WhatsApp deeplink – no phone available",
                extra={"template_key": template_key},
            )
            return ""

        template = (
            self.WHATSAPP_TEMPLATES.get(template_key)
            or self.WHATSAPP_TEMPLATES["GENERIC"]
        )
        # Provide gentle defaults so `.format` does not KeyError when context
        # is missing some optional keys.
        safe_context = {
            "guardian_name": context.get("guardian_name", "Parent"),
            "student_name": context.get("student_name", "your child"),
            "term_name": context.get("term_name", "this term"),
            "portal_link": context.get(
                "portal_link", getattr(settings, "BASE_URL", "")
            ),
            "ticket_id": context.get("ticket_id", ""),
        }
        message = template.format(**safe_context)
        url = self._build_whatsapp_url(phone, message)

        logger.info(
            "Generated WhatsApp deeplink",
            extra={"phone": phone, "template_key": template_key, "url": url},
        )
        return url

    def send_grade_approval_request_email(self, approver, approval_request) -> bool:
        """Notify approvers when a teacher submits grades for review."""
        try:
            base_url = getattr(settings, "BASE_URL", "")
            link = ""
            if base_url:
                link = f"{base_url.rstrip('/')}/evals/grade-approvals/{approval_request.id}/"
            else:
                link = f"/evals/grade-approvals/{approval_request.id}/"

            subject = (
                f"Grade Approval Needed · {approval_request.subject_assignment.subject.name}"
                if approval_request.subject_assignment
                and approval_request.subject_assignment.subject
                else "Grade Approval Requested"
            )
            teacher_name = (
                approval_request.teacher.user.get_full_name()
                if approval_request.teacher and approval_request.teacher.user
                else "Teacher"
            )
            term_label = (
                approval_request.term.label if approval_request.term else "Term"
            )
            year_label = (
                approval_request.academic_year.name
                if approval_request.academic_year
                else "Academic Year"
            )
            _school_signoff = (
                getattr(self.site_settings, "site_name", None)
                or "School Management System"
            )
            body = (
                f"Hello {approver.get_full_name() or approver.username},\n\n"
                f"{teacher_name} has submitted marks for {approval_request.subject_assignment} "
                f"in {term_label} ({year_label}). Review the submission here: {link}\n\n"
                f"Thank you,\n{_school_signoff}"
            )

            send_mail(
                subject=subject,
                message=body,
                from_email=self.site_settings.email_from_address
                if self.site_settings
                else settings.DEFAULT_FROM_EMAIL,
                recipient_list=[approver.email],
            )
            logger.info(f"Grade approval email sent to {approver.email}")
            return True
        except _EVALS_NOTIFICATION_SEND_ERRORS:
            school_id = getattr(
                getattr(approval_request, "academic_year", None), "school_id", None
            ) or getattr(approval_request, "school_id", None)
            log_exception_with_context(
                "evals send_grade_approval_request_email failed",
                school_id=school_id,
                actor_id=getattr(approver, "id", None),
                exc_info=True,
                extra={
                    "recipient": getattr(approver, "email", None),
                    "approval_request_id": getattr(approval_request, "id", None),
                },
            )
            return False

    def send_grade_approval_decision_email(self, approval_request, status) -> bool:
        """Notify the teacher after a decision is recorded."""
        try:
            teacher_user = (
                approval_request.teacher.user if approval_request.teacher else None
            )
            if not teacher_user or not teacher_user.email:
                return False

            status_label = dict(approval_request.Status.choices).get(
                status, status.title()
            )
            subject = (
                f"Grade Approval {status_label} · {approval_request.subject_assignment}"
            )
            _school_signoff = (
                getattr(self.site_settings, "site_name", None)
                or "School Management System"
            )
            body = (
                f"Hello {teacher_user.get_full_name() or teacher_user.username},\n\n"
                f"Your grade submission for {approval_request.subject_assignment} ({approval_request.term.label if approval_request.term else 'Term'}) "
                f"has been marked as {status_label}.\n\n"
                "Check the approval list for details.\n\n"
                f"{_school_signoff}"
            )
            _send_email(
                [teacher_user.email],
                subject=subject,
                body=body,
                site_settings=self.site_settings,
            )
            logger.info(f"Grade approval decision email sent to {teacher_user.email}")
            return True
        except _EVALS_NOTIFICATION_SEND_ERRORS:
            school_id = getattr(
                getattr(approval_request, "academic_year", None), "school_id", None
            ) or getattr(approval_request, "school_id", None)
            log_exception_with_context(
                "evals send_grade_approval_decision_email failed",
                school_id=school_id,
                actor_id=getattr(teacher_user, "id", None),
                exc_info=True,
                extra={
                    "recipient": getattr(teacher_user, "email", None),
                    "approval_request_id": getattr(approval_request, "id", None),
                    "status": status,
                },
            )
            return False
