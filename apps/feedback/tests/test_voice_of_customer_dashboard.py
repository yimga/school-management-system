from django.urls import reverse

from apps.feedback.services import submit_feedback
from .base import FeedbackTestCase


class VoiceOfCustomerDashboardTests(FeedbackTestCase):
    def test_operator_dashboard_renders_feedback(self):
        submit_feedback(
            school=self.school_a,
            user=self.teacher,
            title="Mobile issue",
            description="The mobile report screen clips fields.",
            module="mobile",
        )
        self.force_login_with_mfa(self.operator)
        response = self.client.get(reverse("feedback:voice_of_customer"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mobile issue")
