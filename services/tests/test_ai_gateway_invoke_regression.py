"""Regression-style invoke tests: general_chat + structured doc_classify."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from services.ai_gateway import TaskType, invoke


class GatewayInvokeRegressionTests(TestCase):
    @override_settings(AI_GATEWAY_ENABLED=True)
    @patch(
        "services.ai_gateway._call_ollama",
        return_value=("Hello from campus AI.", {"provider": "ollama", "tier": "ollama"}),
    )
    def test_general_chat_invoke_returns_text(self, _mock_ollama):
        result, meta = invoke(
            TaskType.GENERAL_CHAT,
            "You are a helpful assistant.",
            user_query="What is attendance?",
            metadata={"allowed_backends": ["ollama"]},
        )
        self.assertEqual(result, "Hello from campus AI.")
        self.assertEqual(meta.get("provider"), "ollama")
        self.assertEqual(meta.get("task_type"), TaskType.GENERAL_CHAT.value)
        self.assertTrue(meta.get("request_id"))

    @override_settings(AI_GATEWAY_ENABLED=True)
    @patch(
        "services.ai_gateway._call_ollama",
        return_value=(
            '{"category": "notice", "tags": ["policy"], "confidence": 0.91}',
            {"provider": "ollama", "tier": "ollama"},
        ),
    )
    def test_doc_classify_invoke_returns_validated_dict(self, _mock_ollama):
        result, meta = invoke(
            TaskType.DOC_CLASSIFY,
            "Classify the following document.",
            user_query="Board policy update",
            metadata={"allowed_backends": ["ollama"]},
            response_schema="doc_classify",
        )
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("category"), "notice")
        self.assertIn("policy", result.get("tags", []))
        self.assertGreaterEqual(float(result.get("confidence", 0)), 0.9)
        self.assertFalse(meta.get("schema_validation_failed"))

    @override_settings(AI_GATEWAY_ENABLED=True)
    @patch(
        "services.ai_gateway._call_ollama",
        return_value=("not-json-response", {"provider": "ollama", "tier": "ollama"}),
    )
    def test_doc_classify_invalid_payload_returns_safe_default(self, _mock_ollama):
        result, meta = invoke(
            TaskType.DOC_CLASSIFY,
            "Classify document.",
            user_query="random text",
            metadata={"allowed_backends": ["ollama"]},
            response_schema="doc_classify",
        )
        self.assertEqual(result.get("category"), "general")
        self.assertEqual(result.get("tags"), [])
        self.assertEqual(result.get("confidence"), 0.0)
        self.assertTrue(meta.get("schema_validation_failed"))
