"""Management command evaluate_backlog_unlocks (SLA breach exit)."""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.platform_runtime.backlog_unlock_engine import (
    PROFILE_FULL,
    aging_cache_key,
    states_cache_key,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class EvaluateBacklogUnlocksCommandTests(TestCase):
    def test_fail_on_sla_breach_raises_command_error(self) -> None:
        prof = PROFILE_FULL
        cache.clear()
        cache.set(
            states_cache_key(prof),
            '{"breach_item": "waiting"}',
            timeout=3600,
        )
        cache.set(
            aging_cache_key(prof),
            '{"waiting": {"breach_item": "2020-01-01T00:00:00+00:00"}, "ready_attention": {}}',
            timeout=3600,
        )

        fake_payload = {
            "registry_version": 4,
            "evaluation_profile": prof,
            "items_total_in_registry": 1,
            "items_in_profile": 1,
            "evaluation_profiles_help": {},
            "evaluated_at": "now",
            "repo_root": ".",
            "default_script_timeout": 1,
            "summary": {
                "ready": 0,
                "waiting": 1,
                "ready_attention": 0,
                "blocked_external": 0,
            },
            "items": [
                {
                    "id": "breach_item",
                    "title": "Breach stub",
                    "category": "test",
                    "kind": "verification",
                    "doc_href": "",
                    "action_hint": "",
                    "sot_refs": [],
                    "display_status": "waiting",
                    "criterion_results": [],
                    "max_days_in_waiting": None,
                    "max_days_in_ready_attention": None,
                }
            ],
        }
        registry = {
            "sla": {
                "default_max_days_in_waiting": 21,
                "default_max_days_in_ready_attention": 45,
            },
            "items": [],
        }

        mod = "apps.platform_runtime.management.commands.evaluate_backlog_unlocks"
        with patch(f"{mod}.evaluate_all", return_value=fake_payload), patch(
            f"{mod}.load_registry", return_value=registry
        ):
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "evaluate_backlog_unlocks",
                    profile=prof,
                    fail_on_sla_breach=True,
                    quiet=True,
                )
        self.assertIn("SLA breach", str(ctx.exception))
