"""Google pillar: invoke_with_request auto-redacts heuristic PII."""

from unittest.mock import patch

from django.test import SimpleTestCase

from services.ai_helpers import invoke_with_request, looks_like_pii, redact_pii


class AiHelpersPiiRedactTests(SimpleTestCase):
    def test_redact_pii_masks_email(self):
        out = redact_pii("Contact parent@school.edu for details")
        self.assertNotIn("parent@school.edu", out)
        self.assertIn("[REDACTED-EMAIL]", out)

    def test_invoke_with_request_redacts_before_gateway(self):
        captured: dict = {}

        def fake_invoke(task_type, prompt, **kwargs):
            captured["prompt"] = prompt
            captured["meta"] = kwargs.get("metadata") or {}
            return ("ok", {})

        with patch("services.ai_helpers.is_ai_available", return_value=True):
            with patch("services.ai_gateway.invoke", side_effect=fake_invoke):
                invoke_with_request(
                    task_type="NARRATIVE",
                    prompt="Email parent@example.com about fees",
                    school=object(),
                )
        self.assertTrue(looks_like_pii("parent@example.com"))
        self.assertNotIn("parent@example.com", captured.get("prompt", ""))
        self.assertTrue(captured.get("meta", {}).get("pii_redacted"))
