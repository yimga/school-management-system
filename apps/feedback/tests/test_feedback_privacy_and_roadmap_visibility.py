"""Privacy boundaries and roadmap visibility for feedback surfaces."""

from django.urls import reverse

from apps.feedback.models import FeedbackSubmission
from apps.feedback.services import submit_feedback, visible_roadmap_for_user
from .base import FeedbackTestCase


class FeedbackPrivacyAndRoadmapVisibilityTests(FeedbackTestCase):
    def test_parent_feedback_surface_requires_login(self):
        response = self.client.get(reverse("feedback:parent_feedback"))
        self.assertEqual(response.status_code, 302)

    def test_parent_cannot_see_other_school_private_feedback(self):
        submit_feedback(
            school=self.school_b,
            user=self.operator,
            title="School B only",
            description="Private",
            privacy_level=FeedbackSubmission.PrivacyLevel.SCHOOL_PRIVATE,
        )
        self.force_login_with_mfa(self.parent)
        response = self.client.get(reverse("feedback:parent_feedback"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"School B only", response.content)

    def test_school_roadmap_scoped_to_tenant(self):
        self.force_login_with_mfa(self.admin)
        response = self.client.get(reverse("feedback:school_roadmap"))
        self.assertEqual(response.status_code, 200)
        visible = visible_roadmap_for_user(self.admin, self.school_a)
        self.assertIsNotNone(visible)

    def test_product_roadmap_forbidden_for_tenant_admin(self):
        self.force_login_with_mfa(self.admin)
        response = self.client.get(reverse("feedback:product_roadmap"))
        # These are operator ("/super/") surfaces. On the tenant host a tenant
        # admin cannot reach them at all — the operator route is not mounted in
        # the tenant urlconf, so it 404s (surface hidden), a stronger block than
        # the 302/403 the route returned when it still lived on the tenant host.
        self.assertIn(response.status_code, (302, 403, 404))

    def test_voice_of_customer_forbidden_for_tenant_admin(self):
        self.force_login_with_mfa(self.admin)
        response = self.client.get(reverse("feedback:voice_of_customer"))
        self.assertIn(response.status_code, (302, 403, 404))
