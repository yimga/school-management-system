from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.portal.ai_provider import suggest_support_ticket_response
from apps.schools.models import School


class SuggestSupportTicketResponseTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="AI School",
            slug="ai-school",
            subdomain="ai-school",
            is_active=True,
        )

    @override_settings(AI_GATEWAY_ENABLED=False)
    def test_gateway_disabled_short_circuits(self):
        out, meta = suggest_support_ticket_response("Subj", "Body text", school=self.school)
        self.assertIsNone(out)
        self.assertFalse(meta.get("gateway", True))
        self.assertEqual(meta.get("error"), "disabled")

    @override_settings(AI_GATEWAY_ENABLED=True, SUPPORT_AI_KB_CONTEXT=True)
    @patch("apps.portal.support_ai_context.build_kb_context_block")
    @patch("services.ai_gateway.invoke")
    def test_kb_block_prepended_to_prompt(self, mock_invoke, mock_kb):
        mock_kb.return_value = "KB_BLOCK_HERE"
        mock_invoke.return_value = (
            '{"category":"IT","priority":"NORMAL","suggested_reply":"Try again."}',
            {"gateway": True, "backend": "ollama"},
        )
        data, meta = suggest_support_ticket_response(
            "Password",
            "reset my password please",
            country_code="CM",
            school=self.school,
        )
        self.assertEqual(data.get("category"), "IT")
        self.assertEqual(meta.get("gateway"), True)
        mock_invoke.assert_called_once()
        call_prompt = mock_invoke.call_args[0][1]
        self.assertIn("KB_BLOCK_HERE", call_prompt)
        md = mock_invoke.call_args[1].get("metadata") or {}
        self.assertEqual(md.get("country_code"), "CM")
        self.assertEqual(md.get("school_id"), self.school.pk)

    @override_settings(AI_GATEWAY_ENABLED=True, SUPPORT_AI_KB_CONTEXT=False)
    @patch("services.ai_gateway.invoke")
    def test_explicit_user_id_is_forwarded_to_gateway_metadata(self, mock_invoke):
        mock_invoke.return_value = (
            '{"category":"IT","priority":"NORMAL","suggested_reply":"Try again."}',
            {"gateway": True, "backend": "ollama"},
        )

        data, meta = suggest_support_ticket_response(
            "Password",
            "reset my password please",
            school=self.school,
            user_id="agent-7",
            role="ADMIN",
        )

        self.assertEqual(data.get("category"), "IT")
        self.assertTrue(meta.get("gateway"))
        md = mock_invoke.call_args.kwargs["metadata"]
        self.assertEqual(md.get("user_id"), "agent-7")
        self.assertEqual(md.get("role"), "ADMIN")
        self.assertEqual(md.get("tenant_id"), self.school.pk)

    @override_settings(AI_GATEWAY_ENABLED=True, SUPPORT_AI_KB_CONTEXT=False)
    @patch("services.ai_gateway.invoke")
    def test_json_parse_fallback_wraps_plain_text(self, mock_invoke):
        mock_invoke.return_value = ("Here is a plain reply without JSON.", {"gateway": True})
        data, meta = suggest_support_ticket_response("S", "B", school=None)
        self.assertIn("suggested_reply", data)
        self.assertIn("plain reply", data["suggested_reply"])
