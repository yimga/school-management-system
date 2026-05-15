from apps.feedback.models import FeedbackSubmission
from apps.feedback.services import submit_feedback, visible_feedback_for_user
from .base import FeedbackTestCase


class FeedbackTenantIsolationTests(FeedbackTestCase):
    def test_tenant_user_cannot_see_another_tenant_private_feedback(self):
        submit_feedback(
            school=self.school_b,
            user=self.operator,
            title="Private school B issue",
            description="Do not leak",
            privacy_level=FeedbackSubmission.PrivacyLevel.SCHOOL_PRIVATE,
        )

        visible = visible_feedback_for_user(self.admin, self.school_a)
        self.assertEqual(visible.count(), 0)
