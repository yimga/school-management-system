from django.urls import reverse

from apps.feedback.models import FeedbackSubmission
from apps.feedback.services import submit_feedback
from .base import FeedbackTestCase


class FeedbackSubmissionTests(FeedbackTestCase):
    def test_submit_feedback_records_role_tenant_context(self):
        feedback = submit_feedback(
            school=self.school_a,
            user=self.teacher,
            title="Gradebook tab is slow",
            description="The grade entry workflow is taking too long.",
            category=FeedbackSubmission.Category.WORKFLOW,
            module="gradebook",
            route="/teacher/grades/",
        )

        self.assertEqual(feedback.school, self.school_a)
        self.assertEqual(feedback.role, "TEACHER")
        self.assertEqual(feedback.status, FeedbackSubmission.Status.NEW)
        self.assertEqual(feedback.triage_events.filter(action="submitted").count(), 1)

    def test_school_feedback_view_accepts_submission(self):
        self.force_login_with_mfa(self.admin)
        response = self.client.post(
            reverse("feedback:school_feedback"),
            {
                "form_kind": "feedback",
                "title": "Import mapping is unclear",
                "category": "data_import",
                "module": "imports",
                "route": "/school/setup/imports/",
                "severity": "high",
                "privacy_level": "school_private",
                "contact_preference": "email",
                "description": "Column matching needs clearer warnings.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FeedbackSubmission.objects.filter(module="imports").count(), 1)
