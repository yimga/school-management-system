"""Tests for services.ai_gateway and services.ai_schemas."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from services.ai_gateway import TaskType, invoke, _task_tiers
from services.ai_schemas import (
    extract_json_from_text,
    validate_doc_classify,
    validate_migration_mapping,
    validate_policy_explain,
    validate_workflow_draft,
)


class TaskTiersTests(SimpleTestCase):
    def test_default_task_tiers_include_ollama_rules(self):
        tiers = _task_tiers()
        self.assertIn(TaskType.CONFIG_EXPLAIN.value, tiers)
        self.assertIn(TaskType.WORKFLOW_DRAFT.value, tiers)
        self.assertIn("ollama", tiers.get(TaskType.CONFIG_EXPLAIN.value, []))
        self.assertIn("rules", tiers.get(TaskType.GENERAL_CHAT.value, [])[-1:] or ["rules"])


class InvokeTests(SimpleTestCase):
    @override_settings(AI_GATEWAY_ENABLED=True)
    @patch("services.ai_gateway._call_ollama", return_value=("test response", {"provider": "ollama", "tier": "ollama"}))
    def test_invoke_returns_ollama_result(self, mock_ollama):
        result, meta = invoke(TaskType.CONFIG_EXPLAIN, "Say hello", user_query="hello")
        self.assertEqual(result, "test response")
        self.assertIn(meta.get("provider"), ("ollama", "rules"))
        mock_ollama.assert_called()

    @override_settings(AI_GATEWAY_ENABLED=True, AI_ALLOW_RULES_FALLBACK=True)
    @patch("services.ai_gateway._call_ollama", return_value=(None, {"error": "unavailable"}))
    @patch("services.ai_gateway._call_vllm", return_value=(None, {"error": "unavailable"}))
    def test_invoke_falls_back_to_rules(self, _mock_vllm, _mock_ollama):
        result, meta = invoke(TaskType.CONFIG_EXPLAIN, "Prompt", user_query="query")
        self.assertIsInstance(result, str)
        self.assertIn("query", result or "")
        self.assertEqual(meta.get("provider"), "rules")
        self.assertTrue(meta.get("fallback"))


class SchemaTests(SimpleTestCase):
    def test_validate_workflow_draft(self):
        raw = {"name": "Notify", "trigger_type": "manual", "steps": [{"action": "email", "role": "admin"}], "description": "Send email"}
        out = validate_workflow_draft(raw)
        self.assertEqual(out["name"], "Notify")
        self.assertEqual(len(out["steps"]), 1)
        self.assertEqual(out["steps"][0]["action"], "email")

    def test_validate_policy_explain(self):
        raw = {"summary": "Short", "differences": [{"field": "x", "current": "a", "proposed": "b"}], "warnings": ["w1"]}
        out = validate_policy_explain(raw)
        self.assertEqual(out["summary"], "Short")
        self.assertEqual(len(out["differences"]), 1)
        self.assertEqual(out["warnings"], ["w1"])

    def test_validate_migration_mapping(self):
        raw = [{"source_field": "a", "target_field": "b", "confidence": 0.9, "notes": "ok"}]
        out = validate_migration_mapping(raw)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["source_field"], "a")
        self.assertEqual(out[0]["confidence"], 0.9)

    def test_validate_doc_classify(self):
        raw = {"category": "invoice", "tags": ["finance"], "confidence": 0.85}
        out = validate_doc_classify(raw)
        self.assertEqual(out["category"], "invoice")
        self.assertEqual(out["tags"], ["finance"])
        self.assertEqual(out["confidence"], 0.85)

    def test_extract_json_from_text(self):
        self.assertEqual(extract_json_from_text('pre {"a": 1} post'), {"a": 1})
        self.assertIsNone(extract_json_from_text("no json"))
        self.assertIsNone(extract_json_from_text(""))
