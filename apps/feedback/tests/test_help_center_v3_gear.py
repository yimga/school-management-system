"""Help Center v3 — navigation parity, quick feature, notifications."""

from unittest.mock import patch

from django.urls import reverse

from apps.feedback.models import FeatureRequest

from .base import FeedbackHelpCenterTestCase


class HelpCenterV3GearTests(FeedbackHelpCenterTestCase):
    def test_help_center_quick_feature_post(self):
        self.force_login_with_mfa(self.admin)
        response = self.client.post(
            reverse("feedback:help_center"),
            {
                "form_kind": "feature_quick",
                "title": "Bulk receipt export",
                "problem_statement": "Finance needs CSV export for all receipts.",
                "impact": FeatureRequest.Impact.HIGH,
                "urgency": FeatureRequest.Urgency.SOON,
                "affected_roles": "ADMIN",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            FeatureRequest.objects.filter(title="Bulk receipt export").exists()
        )

    def test_help_center_shows_quick_feature_form(self):
        self.force_login_with_mfa(self.admin)
        response = self.client.get(reverse("feedback:help_center"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Quick feature request", body)
        self.assertIn("feature_quick", body)

    def test_contact_us_platform_message_post(self):
        self.force_login_with_mfa(self.admin)
        response = self.client.post(
            reverse("feedback:contact_us"),
            {
                "form_kind": "platform_message",
                "title": "Need import help",
                "description": "Our CSV import fails on row 42.",
            },
        )
        self.assertEqual(response.status_code, 302)

    @patch("apps.feedback.signals.send_mail", return_value=1)
    def test_feature_request_ack_email_on_create(self, mock_send):
        from apps.feedback.services import submit_feature_request

        # The ack-email handler only writes to a submitter who has an email
        # address (post_save _email_submitter_on_feature_request); the shared
        # base admin is created without one, so set it for this notification path.
        self.admin.email = "admin-ack@example.test"
        self.admin.save(update_fields=["email"])
        submit_feature_request(
            school=self.school_a,
            user=self.admin,
            title="Email ack test",
            problem_statement="Test notification path.",
            affected_roles=["ADMIN"],
            impact=FeatureRequest.Impact.MEDIUM,
            urgency=FeatureRequest.Urgency.SOON,
        )
        self.assertTrue(mock_send.called)
