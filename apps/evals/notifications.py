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
