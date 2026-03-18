from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.siteconfig.brand_import import _normalize_hex_color, fetch_and_parse_brand_url
from apps.siteconfig.design_studio import render_template_to_html
from apps.siteconfig.document_extraction import (
    PatternDocumentExtractionProvider,
    TesseractDocumentExtractionProvider,
    get_document_extraction_provider,
)
from apps.siteconfig.integration_catalog import check_integration_guardrail
from apps.siteconfig.workflow_engine import WorkflowActionExecutionError, run_actions
from apps.siteconfig.workflow_resolver import for_action, get_approval_workflow


class SupportUtilitiesTests(SimpleTestCase):
    def test_normalize_hex_color_supports_short_and_long_values(self):
        self.assertEqual(_normalize_hex_color("#abc"), "#aabbcc")
        self.assertEqual(_normalize_hex_color("A1B2C3"), "#a1b2c3")
        self.assertIsNone(_normalize_hex_color("not-a-color"))

    def test_fetch_and_parse_brand_url_rejects_invalid_url_without_fetch(self):
        result = fetch_and_parse_brand_url("http://")
        self.assertEqual(result["error"], "Invalid URL")
        self.assertIsNone(result["primary_color"])

    def test_render_template_to_html_uses_layout_html(self):
        template = SimpleNamespace(
            layout={"html": "<section><h1>{{ student_name }}</h1>{{ body }}</section>"}
        )
        html = render_template_to_html(template, {"student_name": "Ada", "grade": "A"})
        self.assertIn("<h1>Ada</h1>", html)
        self.assertIn("&lt;strong&gt;grade:&lt;/strong&gt; A", html)

    def test_document_extraction_provider_factory_returns_expected_provider_types(self):
        self.assertIsInstance(
            get_document_extraction_provider("pattern"),
            PatternDocumentExtractionProvider,
        )
        self.assertIsInstance(
            get_document_extraction_provider(
                "ocr_tesseract", tesseract_cmd="/tmp/tesseract"
            ),
            TesseractDocumentExtractionProvider,
        )

    def test_integration_guardrail_respects_daily_cap_and_cooldown(self):
        capped = check_integration_guardrail(
            "sms",
            5,
            usage_getter=lambda school_id, service_key: (500, 0),
        )
        self.assertFalse(capped["allowed"])
        self.assertEqual(capped["reason"], "daily_cap_exceeded")

        throttled = check_integration_guardrail(
            "whatsapp",
            5,
            usage_getter=lambda school_id, service_key: (1, 10**20),
        )
        self.assertFalse(throttled["allowed"])
        self.assertEqual(throttled["reason"], "cooldown")

    def test_run_actions_captures_workflow_action_execution_errors(self):
        with patch(
            "apps.siteconfig.workflow_engine._run_action_notify",
            side_effect=WorkflowActionExecutionError("mail backend unavailable"),
        ):
            results = run_actions(
                [
                    {
                        "type": "notify",
                        "params": {"channel": "email", "to": "ops@example.com"},
                    }
                ],
                {},
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "notify")
        self.assertIn("mail backend unavailable", results[0]["error"])

    def test_for_action_returns_signature_workflow_without_database_access(self):
        self.assertEqual(
            for_action(None, "form_signature"),
            {
                "type": "form_signature",
                "steps": ["pending", "signed", "rejected", "expired"],
            },
        )

    def test_get_approval_workflow_degrades_safely_when_delegation_module_fails(self):
        broken_module = ModuleType("apps.accounts.delegation")

        def _fail(*args, **kwargs):
            raise RuntimeError("delegation unavailable")

        broken_module.get_approval_roles_for_workflow = _fail
        broken_module.get_effective_approvers = _fail
        with patch.dict("sys.modules", {"apps.accounts.delegation": broken_module}):
            result = get_approval_workflow(SimpleNamespace(id=1), "grade_approval")

        self.assertEqual(result["approval_roles"], [])
        self.assertEqual(result["approver_ids"], [])
        self.assertEqual(result["approver_count"], 0)
