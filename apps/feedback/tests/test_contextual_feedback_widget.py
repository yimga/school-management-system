from django.urls import reverse

from apps.feedback.models import FeedbackSubmission
from .base import FeedbackTestCase


class ContextualFeedbackWidgetTests(FeedbackTestCase):
    def test_contextual_feedback_captures_route_module_role(self):
        self.force_login_with_mfa(self.teacher)
        response = self.client.post(
            reverse("feedback:contextual"),
            {
                "title": "Was this page helpful?",
                "description": "Grade page needs clearer save state.",
                "category": "workflow",
                "module": "grades",
                "route": "/teacher/grades/",
                "page_title": "Grades",
            },
        )
        self.assertEqual(response.status_code, 302)
        feedback = FeedbackSubmission.objects.get()
        self.assertEqual(feedback.route, "/teacher/grades/")
        self.assertEqual(feedback.module, "grades")
        self.assertEqual(feedback.role, "TEACHER")

    def test_widget_markup_has_real_action(self):
        self.force_login_with_mfa(self.teacher)
        response = self.client.get(reverse("feedback:teacher_feedback"))
        self.assertEqual(response.status_code, 200)
        # The role feedback center's real action is its own self-posting form,
        # handled by role_feedback_center's POST branch (submit_feedback) — a
        # real submit, not a placeholder link.
        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'type="submit"')
