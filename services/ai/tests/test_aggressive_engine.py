"""Stress tests for engine-room topology, permissions, lifecycle, and throughput."""

from __future__ import annotations

import concurrent.futures
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from services.ai.gateway import process_platform_query
from services.ai.lifecycle import OllamaModelLifecycleManager
from services.ai.reflection import (
    DynamicSystemInspector,
    _append_test_registry_row,
    _clear_test_registry_rows,
    match_path_with_test_hooks,
)
from services.ai.token_optimizer import ContextTokenCompressor


class LiveSystemEvolutionTests(SimpleTestCase):
    def setUp(self):
        _clear_test_registry_rows()

    def tearDown(self):
        _clear_test_registry_rows()

    def test_dynamic_inspector_picks_up_appended_route(self):
        _append_test_registry_row(
            {
                "url_path": "/academics/new-matrix/",
                "required_permissions": ["staff_required", "custom:CanModifySchedules"],
                "allowable_methods": ["GET", "POST"],
            }
        )
        inspector = DynamicSystemInspector()
        row = match_path_with_test_hooks(inspector, "/academics/new-matrix/edit")
        self.assertIsNotNone(row)
        self.assertIn("staff_required", row.get("required_permissions", []))


class PermissionEnforcementTests(SimpleTestCase):
    @override_settings(AI_GATEWAY_ENABLED=True, AI_ENGINE_ROOM_SUPPORT=True)
    def test_teacher_finance_query_refused_without_model(self):
        user = SimpleNamespace(
            role="TEACHER",
            is_staff=False,
            is_superuser=False,
            is_authenticated=True,
            pk=1,
        )
        with patch("services.ai.gateway.retrieve_knowledge_snippets") as mock_kb:
            mock_kb.return_value = (["- KB: ledger doc"], [{"scope": "help"}])
            with patch("services.ai_gateway.invoke") as mock_invoke:
                out = process_platform_query(
                    user,
                    "/finance/ledger/",
                    "How do I clear out financial ledgers for the term?",
                    school=SimpleNamespace(pk="school-a"),
                )
        mock_invoke.assert_not_called()
        self.assertTrue(out.get("success"))
        self.assertIn("ledger", out.get("response", "").lower())


class HotReloadResiliencyTests(SimpleTestCase):
    def test_lifecycle_rollback_on_pull_failure(self):
        mgr = OllamaModelLifecycleManager(endpoint="http://127.0.0.1:9", target_model="llama3")
        with patch.object(mgr, "list_local_models", return_value=[]):
            with patch.object(mgr, "_post_json", side_effect=OSError("network down")):
                report = mgr.check_and_update_model(pull_if_missing=True)
        self.assertFalse(report.get("healthy"))
        self.assertIsNotNone(report.get("error"))
        rolled = mgr.rollback_to_previous()
        self.assertEqual(rolled, "llama3")


class ThroughputTests(SimpleTestCase):
    @override_settings(AI_GATEWAY_ENABLED=True, AI_ENGINE_ROOM_SUPPORT=True)
    def test_concurrent_queries_do_not_raise(self):
        user = SimpleNamespace(
            role="ADMIN",
            is_staff=True,
            is_superuser=False,
            is_authenticated=True,
            pk=99,
        )

        def _one(_: int):
            with patch(
                "services.ai.gateway.retrieve_knowledge_snippets",
                return_value=([], []),
            ):
                return process_platform_query(
                    user, "/help/", "reset grading period", school=None
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(_one, i) for i in range(50)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        self.assertEqual(len(results), 50)
        for item in results:
            self.assertTrue(item.get("escalation_required"))


class TokenCompressorTests(SimpleTestCase):
    def test_bloated_context_truncates(self):
        compressor = ContextTokenCompressor(max_input_tokens=200)
        huge = "word " * 5000
        out = compressor.compress(
            permission_block="role: ADMIN",
            screen_block="/dashboard/",
            knowledge_block=huge,
            history_block=huge,
        )
        self.assertTrue(out.truncated)
        self.assertLess(len(out.knowledge_block), len(huge))
