"""Notification service for SMS, email, digests."""

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings
import logging
from typing import List

logger = logging.getLogger(__name__)


class NotificationService:
    """Handles SMS, Email, digests."""
    
    def __init__(self):
        self.site_settings = settings.SITE_SETTINGS if hasattr(settings, 'SITE_SETTINGS') else None
    
    def send_grade_publication_email(self, student, term, recipient_email):
        """Email when grades published."""
        try:
            context = {
                'student_name': student.get_full_name(),
                'term_name': term.label,
                'academic_year': term.academic_year.name,
                'portal_link': f"{settings.BASE_URL}/portal/parent/results/{student.id}/" if hasattr(settings, 'BASE_URL') else '#',
            }
            
            html_message = render_to_string('emails/grade_publication.html', context)
            plain_message = render_to_string('emails/grade_publication.txt', context)
            
            send_mail(
                subject=f"Report Card: {student.get_full_name()} - {term.label}",
                message=plain_message,
                from_email=self.site_settings.email_from_address if self.site_settings else settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                html_message=html_message,
            )
            
            logger.info(f"Grade publication email sent to {recipient_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send grade publication email: {e}")
            return False
    
    def send_grade_publication_sms(self, guardian, student, term):
        """SMS with link when grades published."""
        try:
            portal_link = f"{settings.BASE_URL}/portal/results/{student.id}/" if hasattr(settings, 'BASE_URL') else 'portal'
            message = (
                f"Hi {guardian.guardian_user.first_name}, "
                f"{student.get_full_name()}'s {term.label} report is ready. "
                f"View: {portal_link}"
            )
            return self.send_sms(guardian.phone, message)
        except Exception as e:
            logger.error(f"Failed to send grade publication SMS: {e}")
            return False
    
    def send_deadline_reminder_email(self, teacher, deadline_at, subject_count):
        """Email reminder to teacher."""
        try:
            days_left = (deadline_at - timezone.now()).days
            
            context = {
                'teacher_name': teacher.get_full_name(),
                'deadline_at': deadline_at,
                'days_left': days_left,
                'subject_count': subject_count,
                'entry_link': f"{settings.BASE_URL}/evals/teacher/marks/entry/" if hasattr(settings, 'BASE_URL') else '#',
            }
            
            html_message = render_to_string('emails/deadline_reminder.html', context)
            plain_message = render_to_string('emails/deadline_reminder.txt', context)
            
            send_mail(
                subject=f"Grading Deadline Reminder: {deadline_at.strftime('%B %d')}",
                message=plain_message,
                from_email=self.site_settings.email_from_address if self.site_settings else settings.DEFAULT_FROM_EMAIL,
                recipient_list=[teacher.user.email],
                html_message=html_message,
            )
            
            logger.info(f"Deadline reminder email sent to {teacher.user.email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send deadline reminder: {e}")
            return False
    
    def send_sms(self, phone_number: str, message: str) -> bool:
        """Send SMS via configured provider."""
        if not self.site_settings:
            logger.info(f"[CONSOLE SMS] {phone_number}: {message}")
            return True
        
        provider = self.site_settings.sms_provider
        
        if provider == 'twilio':
            return self._send_sms_twilio(phone_number, message)
        elif provider == 'africastalking':
            return self._send_sms_africastalking(phone_number, message)
        else:
            logger.info(f"[CONSOLE SMS] {phone_number}: {message}")
            return True

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
                if approval_request.subject_assignment and approval_request.subject_assignment.subject
                else "Grade Approval Requested"
            )
            teacher_name = (
                approval_request.teacher.user.get_full_name()
                if approval_request.teacher and approval_request.teacher.user
                else "Teacher"
            )
            term_label = approval_request.term.label if approval_request.term else "Term"
            year_label = approval_request.academic_year.name if approval_request.academic_year else "Academic Year"
            body = (
                f"Hello {approver.get_full_name() or approver.username},\n\n"
                f"{teacher_name} has submitted marks for {approval_request.subject_assignment} "
                f"in {term_label} ({year_label}). Review the submission here: {link}\n\n"
                "Thank you,\nSchool Management System"
            )

            send_mail(
                subject=subject,
                message=body,
                from_email=self.site_settings.email_from_address if self.site_settings else settings.DEFAULT_FROM_EMAIL,
                recipient_list=[approver.email],
            )
            logger.info(f"Grade approval email sent to {approver.email}")
            return True
        except Exception as exc:
            logger.error("Failed to send grade approval email", exc_info=exc)
            return False

    def send_grade_approval_decision_email(self, approval_request, status) -> bool:
        """Notify the teacher after a decision is recorded."""
        try:
            teacher_user = approval_request.teacher.user if approval_request.teacher else None
            if not teacher_user or not teacher_user.email:
                return False

            status_label = dict(approval_request.Status.choices).get(status, status.title())
            subject = f"Grade Approval {status_label} · {approval_request.subject_assignment}"
            body = (
                f"Hello {teacher_user.get_full_name() or teacher_user.username},\n\n"
                f"Your grade submission for {approval_request.subject_assignment} ({approval_request.term.label if approval_request.term else 'Term'}) "
                f"has been marked as {status_label}.\n\n"
                "Check the approval list for details.\n\n"
                "School Management System"
            )
            send_mail(
                subject=subject,
                message=body,
                from_email=self.site_settings.email_from_address if self.site_settings else settings.DEFAULT_FROM_EMAIL,
                recipient_list=[teacher_user.email],
            )
            logger.info(f"Grade approval decision email sent to {teacher_user.email}")
            return True
        except Exception as exc:
            logger.error("Failed to send grade approval decision email", exc_info=exc)
            return False
    
    def _send_sms_twilio(self, phone_number: str, message: str) -> bool:
        """Twilio SMS."""
        try:
            from twilio.rest import Client
            client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN
            )
            msg = client.messages.create(
                body=message,
                from_=self.site_settings.sms_sender_id,
                to=phone_number,
            )
            logger.info(f"SMS sent via Twilio: {msg.sid}")
            return True
        except Exception as e:
            logger.error(f"Twilio SMS failed: {e}")
            return False
    
    def _send_sms_africastalking(self, phone_number: str, message: str) -> bool:
        """AfricasTalking SMS."""
        try:
            import africastalking
            at = africastalking.SMS(api_key=self.site_settings.sms_api_key)
            response = at.send(
                message,
                [phone_number],
                sender_id=self.site_settings.sms_sender_id
            )
            logger.info(f"SMS sent via AfricasTalking: {response}")
            return True
        except Exception as e:
            logger.error(f"AfricasTalking SMS failed: {e}")
            return False
