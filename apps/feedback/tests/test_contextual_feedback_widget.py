from django.urls import reverse

from apps.feedback.models import FeedbackSubmission
from .base import FeedbackTestCase


class ContextualFeedbackWidgetTests(FeedbackTestCase):
    def test_contextual_feedback_captures_route_module_role(self):
        self.client.force_login(self.teacher)
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
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("feedback:teacher_feedback"))
        self.assertContains(response, reverse("feedback:contextual"))
        self.assertNotContains(response, 'href="#"')
