from django.test import Client
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
        # voice_of_customer is an operator ("/super/") surface routed on the
        # manager host (config.manager_urls includes feedback.urls), NOT on the
        # tenant host the base client uses (feedback.tenant_urls omits operator
        # surfaces). Reach it as an operator on the manager host.
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.force_login(self.operator)
        session = client.session
        session["mfa_verified"] = True
        session.save()
        response = client.get(reverse("feedback:voice_of_customer"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mobile issue")
