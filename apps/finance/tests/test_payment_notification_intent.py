"""SFDP 1431 — payment.received notification intents."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.schoolops.notification_intent import render_notification_intent
from apps.schoolops.sms_templates import render_payment_received_sms


class PaymentNotificationIntentTests(TestCase):
    def test_render_payment_received_email(self):
        subject, body, html = render_notification_intent(
            template_key="payment_received",
            locale="en",
            context={
                "student_name": "Ada",
                "amount": "100.00",
                "currency": "NGN",
                "reference": "INV-1",
            },
        )
        self.assertIn("Payment received", subject)
        self.assertIn("Ada", body)
        self.assertIsNone(html)

    def test_render_payment_received_sms_under_160(self):
        body = render_payment_received_sms(
            locale="en",
            context={"student_name": "Ada", "reference": "INV-1"},
        )
        self.assertLessEqual(len(body), 160)
        self.assertIn("Ada", body)

    @patch("apps.schoolops.email_delivery.send_transactional")
    def test_dispatch_skips_without_school(self, mock_send):
        from apps.finance.payment_notification_intent import dispatch_payment_received_intent

        result = dispatch_payment_received_intent(school=None, payment=None)
        self.assertEqual(result["dispatched"], 0)
        mock_send.assert_not_called()

    def test_guardian_contacts_resolved_for_payment(self):
        """Regression: ``_guardian_contacts_for_payment`` used a non-existent
        ``select_related("guardian", ...)`` relation on StudentGuardian (its
        relations are guardian_user + student), so the FieldError was silently
        swallowed and guardian contacts ALWAYS resolved to [] — payment-received
        intents never reached anyone. The contact must now resolve."""
        from decimal import Decimal

        from apps.accounts.models import User
        from apps.finance.models import Payment
        from apps.finance.payment_notification_intent import (
            _guardian_contacts_for_payment,
        )
        from apps.people.models import StudentGuardian, StudentProfile
        from apps.schools.models import School

        school = School.objects.create(
            name="Contacts", slug="contacts-school", subdomain="contacts-school"
        )
        student = StudentProfile.objects.create(
            school=school,
            first_name="Ada",
            last_name="Lovelace",
            student_code="STU-CONTACT-1",
            date_of_birth="2013-05-10",
        )
        parent = User.objects.create_user(
            username="parent@contacts.test",
            email="parent-user@contacts.test",
            password="x",
            role=User.Role.PARENT,
        )
        StudentGuardian.objects.create(
            guardian_user=parent,
            student=student,
            email="guardian-link@contacts.test",
            phone="+237600000000",
        )

        # Unsaved Payment -> exercise the resolver directly, no save-signal machinery.
        payment = Payment(school=school, student=student, amount=Decimal("100.00"))
        contacts = _guardian_contacts_for_payment(payment)

        self.assertEqual(len(contacts), 1)
        email, phone = contacts[0]
        # Link's own email column is preferred; phone resolves from the link.
        self.assertEqual(email, "guardian-link@contacts.test")
        self.assertEqual(phone, "+237600000000")
