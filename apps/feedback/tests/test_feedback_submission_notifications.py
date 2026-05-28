"""Batch 1519 — feedback submission notification loop."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from apps.customersuccess.models import AutoTicketRule
from apps.feedback.models import FeedbackSubmission
from apps.schools.models import School, SchoolMembership

User = get_user_model()


@override_settings(
    OPERATOR_ALERT_EMAIL="ops-alert@example.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class FeedbackSubmissionNotificationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Notify School",
            slug="notify-school",
            subdomain="notify-school",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username="notify-admin",
            email="admin-notify@example.test",
            password="pass",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )
        AutoTicketRule.objects.create(
            name="Critical feedback",
            trigger=AutoTicketRule.Trigger.FEEDBACK_CRITICAL,
            is_active=True,
        )
        mail.outbox.clear()

    def test_critical_submission_emails_operator_and_admin(self):
        FeedbackSubmission.objects.create(
            school=self.school,
            user=self.admin,
            title="Cannot pay fees",
            description="Checkout fails on every attempt.",
            category=FeedbackSubmission.Category.BILLING,
            severity=FeedbackSubmission.Severity.CRITICAL,
        )
        recipients = sorted({addr for msg in mail.outbox for addr in msg.to})
        self.assertIn("ops-alert@example.test", recipients)
        self.assertIn("admin-notify@example.test", recipients)

    def test_medium_submission_does_not_alert(self):
        FeedbackSubmission.objects.create(
            school=self.school,
            user=self.admin,
            title="Minor UI nit",
            description="Button spacing.",
            severity=FeedbackSubmission.Severity.MEDIUM,
        )
        self.assertEqual(mail.outbox, [])

    def test_auto_ticket_rule_creates_feedback_row(self):
        before = FeedbackSubmission.objects.count()
        FeedbackSubmission.objects.create(
            school=self.school,
            user=self.admin,
            title="Urgent outage",
            description="Portal down for parents.",
            severity=FeedbackSubmission.Severity.HIGH,
        )
        after = FeedbackSubmission.objects.count()
        self.assertEqual(after - before, 2)
        auto_row = None
        for row in FeedbackSubmission.objects.order_by("-created_at")[:5]:
            if "auto_ticket_feedback_critical" in (row.tags or []):
                auto_row = row
                break
        self.assertIsNotNone(auto_row)
        self.assertIn("auto_ticket", auto_row.tags)
