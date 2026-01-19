from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.finance.models import (
    PaymentReminder,
    PaymentReminderLog,
)
from apps.finance.services import generate_payment_link
from apps.people.models import StudentGuardian
from apps.siteconfig.models import Integration


class Command(BaseCommand):
    help = "Send payment reminders for upcoming invoice due dates."

    def handle(self, *args, **options):
        now = timezone.now()
        reminders = PaymentReminder.objects.filter(is_active=True, next_send_at__lte=now)

        if not reminders:
            self.stdout.write("No reminders due.")
            return

        integration = Integration.objects.filter(provider="email", enabled=True).first()

        for reminder in reminders:
            invoice = reminder.invoice
            guardians = StudentGuardian.objects.filter(
                student=invoice.student,
                can_view_finance=True,
                guardian_user__is_active=True,
            ).select_related("guardian_user")

            if not guardians:
                self.stdout.write(f"No guardians configured for invoice {invoice}.")
                continue

            payment_link = generate_payment_link(invoice)
            default_link = getattr(settings, "SITE_URL", "https://school.example/")
            link_display = payment_link["url"] if payment_link else default_link
            subject = f"[Reminder] Pay {invoice.reference or invoice.id}"
            due_display = invoice.due_date or timezone.localdate(now)

            for guardian in guardians:
                body = reminder.message_template.format(
                    guardian=guardian.guardian_user.get_full_name() or guardian.guardian_user.username,
                    amount=invoice.balance_amount,
                    invoice=invoice.reference or invoice.id,
                    due_date=due_display,
                    link=link_display,
                )
                to_email = guardian.guardian_user.email or ""
                self._send_email(to_email, subject, body, integration)
                PaymentReminderLog.objects.create(
                    reminder=reminder,
                    status="SENT",
                    note=f"Email sent to {to_email}",
                )

            reminder.last_sent_at = now
            reminder.schedule_next()
            reminder.save(update_fields=["last_sent_at", "next_send_at"])
            self.stdout.write(f"Sent reminder for invoice {invoice.reference or invoice.id}.")

    def _send_email(self, to_email: str, subject: str, body: str, integration: Integration | None):
        if not to_email:
            return

        from_email = settings.DEFAULT_FROM_EMAIL
        if integration and integration.config:
            from_email = integration.config.get("from_email", from_email)

        email = EmailMessage(subject, body, from_email, [to_email])
        email.send(fail_silently=True)
