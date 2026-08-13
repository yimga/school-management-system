"""Phase 5 — the edge-device flag gates everything, so other tenants are untouched.

RMC_EDGE_SYNC_ENABLED off (every ordinary cloud tenant, the default):
  * the two-way entity registry is EXACTLY the original three entities, and
  * the scheduled edge_sync_cycle is a pure no-op (no push, no pull, no network).

RMC_EDGE_SYNC_ENABLED on (the sovereign edge box):
  * the expanded Class-A registry is available, and
  * edge_sync_cycle runs both directions.
"""
from __future__ import annotations

from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from apps.api.sync_services import _get_entity_config

_ORIGINAL_THREE = {"student", "attendance", "classroom"}
_DERIVED = {"applicant", "student_note", "academic_year", "term", "department"}

_CYCLE = "apps.sync_engine.management.commands.edge_sync_cycle.call_command"


class EntityRegistryGatingTests(SimpleTestCase):
    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_flag_off_keeps_exactly_the_original_three(self):
        self.assertEqual(set(_get_entity_config()), _ORIGINAL_THREE)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_flag_on_adds_the_derived_class_a_entities(self):
        entities = set(_get_entity_config())
        self.assertTrue(_ORIGINAL_THREE <= entities)
        self.assertTrue(_DERIVED <= entities, entities)


class EdgeSyncCycleGateTests(SimpleTestCase):
    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_cycle_is_noop_when_flag_off(self):
        with patch(_CYCLE) as sub:
            # No error, and crucially it never invokes the push/pull sub-commands or
            # touches the network — even without slug/operator/token.
            call_command("edge_sync_cycle")
        sub.assert_not_called()

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_cycle_runs_push_then_pull_when_flag_on(self):
        with patch(_CYCLE) as sub:
            call_command("edge_sync_cycle", slug="gilead", operator_base="https://op.example")
        self.assertEqual(sub.call_count, 2, sub.call_args_list)
        self.assertEqual(sub.call_args_list[0].args[0], "post_edge_outbox")
        self.assertEqual(sub.call_args_list[1].args[0], "pull_edge_inbox")
