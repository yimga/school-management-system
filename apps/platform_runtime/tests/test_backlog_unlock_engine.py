"""Tests for backlog unlock registry engine (no heavy script runs by default)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.platform_runtime.backlog_unlock_engine import (
    PROFILE_FULL,
    apply_sla_enrichment,
    diff_emit_ready_transitions,
    evaluate_all,
    item_in_profile,
    load_registry,
    merge_aging_timestamps,
    normalize_profile,
    registry_path,
)


class BacklogUnlockEngineTests(SimpleTestCase):
    def test_registry_file_exists(self) -> None:
        p = registry_path()
        self.assertTrue(p.is_file(), f"missing {p}")

    def test_load_registry_has_items(self) -> None:
        data = load_registry()
        self.assertGreaterEqual(int(data.get("registry_version", 0)), 4)
        self.assertGreaterEqual(len(data.get("items") or []), 10)
        ep = data.get("evaluation_profiles")
        self.assertIsInstance(ep, dict)
        self.assertIn("smoke", ep)
        self.assertIn("full", ep)
        sla = data.get("sla")
        self.assertIsInstance(sla, dict)
        self.assertIn("default_max_days_in_waiting", sla)

    def test_normalize_profile(self) -> None:
        self.assertEqual(normalize_profile(None), PROFILE_FULL)
        self.assertEqual(normalize_profile(""), PROFILE_FULL)
        self.assertEqual(normalize_profile("smoke"), "smoke")
        self.assertEqual(normalize_profile("SMOKE"), "smoke")
        self.assertEqual(normalize_profile("nope"), PROFILE_FULL)

    def test_smoke_profile_filters_registry_items(self) -> None:
        root = Path(__file__).resolve().parent.parent.parent.parent
        stub = {
            "registry_version": 3,
            "evaluation_profiles": {"smoke": "fast", "full": "all"},
            "items": [
                {
                    "id": "full_only",
                    "title": "Full only",
                    "category": "test",
                    "kind": "verification",
                    "profiles": ["full"],
                    "criteria": [],
                },
                {
                    "id": "both",
                    "title": "Smoke and full",
                    "category": "test",
                    "kind": "verification",
                    "profiles": ["smoke", "full"],
                    "criteria": [],
                },
                {
                    "id": "default_full",
                    "title": "Default full",
                    "category": "test",
                    "kind": "verification",
                    "criteria": [],
                },
            ],
        }
        with patch(
            "apps.platform_runtime.backlog_unlock_engine.load_registry",
            return_value=stub,
        ):
            smoke = evaluate_all(root, profile="smoke", default_script_timeout=1)
            full = evaluate_all(root, profile="full", default_script_timeout=1)
        self.assertEqual(smoke["items_total_in_registry"], 3)
        self.assertEqual(smoke["items_in_profile"], 1)
        self.assertEqual(smoke["items"][0]["id"], "both")
        self.assertEqual(full["items_in_profile"], 3)
        self.assertEqual(full["evaluation_profile"], "full")
        raw_both = next(x for x in stub["items"] if x["id"] == "both")
        self.assertTrue(item_in_profile(raw_both, "smoke"))
        raw_only = next(x for x in stub["items"] if x["id"] == "full_only")
        self.assertFalse(item_in_profile(raw_only, "smoke"))

    def test_external_blocker_status(self) -> None:
        root = Path(__file__).resolve().parent.parent.parent.parent
        stub = {
            "registry_version": 1,
            "items": [
                {
                    "id": "ext_stub",
                    "title": "External stub",
                    "category": "external_org",
                    "kind": "external_blocker",
                    "criteria": [],
                }
            ],
        }
        with patch(
            "apps.platform_runtime.backlog_unlock_engine.load_registry",
            return_value=stub,
        ):
            payload = evaluate_all(root, default_script_timeout=1)
        self.assertEqual(payload["items"][0]["display_status"], "blocked_external")

    def test_evaluate_all_with_mock_script(self) -> None:
        root = Path(__file__).resolve().parent.parent.parent.parent

        def fake_run(repo_root, script, args, timeout):
            if "lint_tenant_settings" in script:
                return True, "ok"
            return False, "fail"

        custom_items = {
            "registry_version": 99,
            "items": [
                {
                    "id": "t_mock_ok",
                    "title": "Mock ok",
                    "category": "test",
                    "kind": "verification",
                    "criteria": [
                        {
                            "type": "script_exit_zero",
                            "script": "scripts/lint_tenant_settings.py",
                            "args": ["--check-get-solo-only", "--base", "."],
                            "timeout_seconds": 5,
                        }
                    ],
                }
            ],
        }
        with patch(
            "apps.platform_runtime.backlog_unlock_engine.load_registry",
            return_value=custom_items,
        ), patch(
            "apps.platform_runtime.backlog_unlock_engine._run_script",
            side_effect=fake_run,
        ):
            payload = evaluate_all(root, default_script_timeout=5)
        self.assertEqual(payload["registry_version"], 99)
        row = payload["items"][0]
        self.assertEqual(row["display_status"], "ready")

    def test_diff_emit_transitions(self) -> None:
        prev = {"a": "waiting", "b": "ready"}
        cur = {"a": "ready", "b": "ready", "c": "ready_attention"}
        d = diff_emit_ready_transitions(prev, cur)
        self.assertTrue(any(t[0] == "a" and t[2] == "ready" for t in d))

    def test_pytest_criterion_ready_when_pytest_passes(self) -> None:
        root = Path(__file__).resolve().parent.parent.parent.parent
        stub = {
            "registry_version": 2,
            "items": [
                {
                    "id": "pytest_stub",
                    "title": "Pytest stub",
                    "category": "test",
                    "kind": "verification",
                    "criteria": [
                        {
                            "type": "pytest_exit_zero",
                            "targets": ["apps/platform_runtime/tests/test_backlog_unlock_engine.py"],
                            "args": ["-q", "--no-header"],
                            "timeout_seconds": 120,
                        }
                    ],
                }
            ],
        }
        with patch(
            "apps.platform_runtime.backlog_unlock_engine.load_registry",
            return_value=stub,
        ), patch(
            "apps.platform_runtime.backlog_unlock_engine._run_pytest",
            return_value=(True, "exit 0"),
        ) as mock_pt:
            payload = evaluate_all(root, default_script_timeout=5)
        mock_pt.assert_called_once()
        self.assertEqual(payload["items"][0]["display_status"], "ready")
        res = payload["items"][0]["criterion_results"][0]
        self.assertEqual(res["type"], "pytest_exit_zero")
        self.assertTrue(res["ok"])

    def test_merge_aging_resets_on_re_enter_waiting(self) -> None:
        now = "2026-03-25T12:00:00+00:00"
        later = "2026-03-26T12:00:00+00:00"
        items = [{"id": "a", "display_status": "waiting"}]
        ag0 = merge_aging_timestamps({}, items, {}, now)
        self.assertEqual(ag0["waiting"]["a"], now)
        prev = {"a": "waiting"}
        ag1 = merge_aging_timestamps(prev, items, ag0, later)
        self.assertEqual(ag1["waiting"]["a"], now)
        items2 = [{"id": "a", "display_status": "ready"}]
        ag2 = merge_aging_timestamps({"a": "waiting"}, items2, ag1, later)
        self.assertNotIn("a", ag2["waiting"])
        items3 = [{"id": "a", "display_status": "waiting"}]
        ag3 = merge_aging_timestamps({"a": "ready"}, items3, ag2, later)
        self.assertEqual(ag3["waiting"]["a"], later)

    def test_apply_sla_marks_breach_for_old_waiting(self) -> None:
        payload = {
            "items": [
                {
                    "id": "w1",
                    "display_status": "waiting",
                    "kind": "verification",
                }
            ]
        }
        aging = {
            "waiting": {"w1": "2020-01-01T00:00:00+00:00"},
            "ready_attention": {},
        }
        registry = {
            "sla": {
                "default_max_days_in_waiting": 21,
                "default_max_days_in_ready_attention": 45,
            }
        }
        apply_sla_enrichment(payload, aging, registry)
        it = payload["items"][0]
        self.assertTrue(it["sla_waiting_breached"])
        self.assertGreater(it["days_in_waiting"], 100)
        sm = payload["sla_summary"]
        self.assertGreaterEqual(sm["breached_waiting"], 1)

    def test_program_partial_counts_pytest_criteria(self) -> None:
        root = Path(__file__).resolve().parent.parent.parent.parent
        stub = {
            "registry_version": 2,
            "items": [
                {
                    "id": "pp_pytest",
                    "title": "Partial + pytest",
                    "category": "test",
                    "kind": "program_partial",
                    "criteria": [
                        {
                            "type": "pytest_exit_zero",
                            "targets": ["apps/x/test_y.py"],
                            "timeout_seconds": 5,
                        }
                    ],
                }
            ],
        }
        with patch(
            "apps.platform_runtime.backlog_unlock_engine.load_registry",
            return_value=stub,
        ), patch(
            "apps.platform_runtime.backlog_unlock_engine._run_pytest",
            return_value=(True, "ok"),
        ):
            payload = evaluate_all(root, default_script_timeout=5)
        self.assertEqual(payload["items"][0]["display_status"], "ready_attention")
