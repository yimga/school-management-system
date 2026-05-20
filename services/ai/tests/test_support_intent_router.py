"""Intent router tests (batch 1333) — canonical filename for CI/prompt alignment."""

from django.test import SimpleTestCase

from services.ai.support_intent import SupportIntent, classify_support_intent


class SupportIntentRouterTests(SimpleTestCase):
    def test_ui_help_from_navigation_phrase(self):
        intent = classify_support_intent("Where is the grading tab?", active_url="/grades/")
        self.assertEqual(intent, SupportIntent.UI_NAVIGATION_HELP)

    def test_api_dev_from_webhook_query(self):
        intent = classify_support_intent(
            "How do I verify webhook signature headers?",
            active_url="/api/v1/schema/",
        )
        self.assertEqual(intent, SupportIntent.API_DEVELOPER_SUPPORT)

    def test_troubleshooting_from_error_token(self):
        intent = classify_support_intent("Save failed with 500 error", active_url="/portal/")
        self.assertEqual(intent, SupportIntent.TROUBLESHOOTING_ERROR)
