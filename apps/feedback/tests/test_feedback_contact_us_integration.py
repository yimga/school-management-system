"""Public contact + in-app help/feedback loop integration."""

from django.test import Client, override_settings
from django.urls import reverse

from .base import FeedbackTestCase


@override_settings(ALLOWED_HOSTS=["*"])
class FeedbackContactUsIntegrationTests(FeedbackTestCase):
    def test_marketing_contact_page_reachable(self):
        client = Client(HTTP_HOST="runmycampus.com", raise_request_exception=False)
        response = client.get(reverse("marketing_contact"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("contact", body.lower())

    def test_help_center_bridges_feedback_after_login(self):
        self.force_login_with_mfa(self.admin)
        help_resp = self.client.get(reverse("feedback:help_center"))
        self.assertEqual(help_resp.status_code, 200)
        feedback_resp = self.client.get(reverse("feedback:school_feedback"))
        self.assertEqual(feedback_resp.status_code, 200)

    def test_contextual_feedback_endpoint_accepts_post(self):
        self.force_login_with_mfa(self.teacher)
        response = self.client.post(
            reverse("feedback:contextual"),
            {
                "title": "Button unclear",
                "description": "Save action needs a label",
                "category": "general",
            },
        )
        self.assertIn(response.status_code, (302, 200))
