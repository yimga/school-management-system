"""Public contact + in-app help/feedback loop integration."""

from django.test import Client, override_settings
from django.urls import reverse

from apps.feedback.models import FeatureRequest

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
        body = help_resp.content.decode("utf-8", errors="replace")
        self.assertIn(reverse("feedback:contact_us"), body)
        self.assertIn(reverse("feedback:feature_center"), body)
        self.assertIn(reverse("kb:faq_list"), body)
        feedback_resp = self.client.get(reverse("feedback:school_feedback"))
        self.assertEqual(feedback_resp.status_code, 200)

    def test_authenticated_contact_us_router_exposes_human_and_product_lanes(self):
        self.force_login_with_mfa(self.admin)
        response = self.client.get(reverse("feedback:contact_us"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Platform support", body)
        self.assertIn("Product feedback", body)
        self.assertIn(reverse("portal:support_request"), body)
        self.assertIn(reverse("feedback:school_feedback"), body)
        self.assertIn(reverse("feedback:feature_center"), body)

    def test_feature_center_submits_and_lists_feature_requests(self):
        self.force_login_with_mfa(self.admin)
        response = self.client.post(
            reverse("feedback:feature_center"),
            {
                "title": "Bulk receipt resend",
                "problem_statement": "Finance staff need to resend a batch of receipts.",
                "proposed_solution": "Add bulk resend from the payments screen.",
                "current_workaround": "Open each family profile.",
                "affected_roles": "bursar,parent",
                "module": "finance",
                "impact": FeatureRequest.Impact.HIGH,
                "urgency": FeatureRequest.Urgency.THIS_TERM,
                "school_type": "k12",
                "region": "CM",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            FeatureRequest.objects.filter(
                school=self.school_a,
                title="Bulk receipt resend",
                affected_roles=["BURSAR", "PARENT"],
            ).exists()
        )
        response = self.client.get(reverse("feedback:feature_center"))
        self.assertContains(response, "Bulk receipt resend")

    def test_parent_and_student_do_not_enter_feature_center_complexity(self):
        # Non-staff are steered out of the feature-center by the help-governance
        # guard (``should_redirect_feature_center_for_request``: "feature voting
        # is for staff"), which fires ahead of the role-specific redirects and
        # sends parents/students to the Help Center.
        help_center_url = reverse("feedback:help_center")
        self.force_login_with_mfa(self.parent)
        response = self.client.get(reverse("feedback:feature_center"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, help_center_url)

        self.client.logout()
        self.force_login_with_mfa(self.student)
        response = self.client.get(reverse("feedback:feature_center"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, help_center_url)

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
