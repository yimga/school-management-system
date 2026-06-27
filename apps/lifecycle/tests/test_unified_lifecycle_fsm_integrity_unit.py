"""No-DB unit tests for the unified-lifecycle FSM-integrity gate (Wave C, #1).

Mirrors scripts/verify_unified_lifecycle_fsm_integrity.py so the FSM's
structural invariants are provable without a database (importing the module
classes does not query the DB). SimpleTestCase keeps this in the fast,
DB-less suite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from django.test import SimpleTestCase

from apps.lifecycle import unified_lifecycle as ul
from apps.lifecycle.models import SchoolLifecycleStage

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_gate():
    """Load the standalone gate by path (it lives under scripts/, not a package).

    Reads the gate's real ``find_errors`` / ``_reachable_from`` so this test
    exercises the SAME logic CI runs, not a hand-copied reimplementation.
    """
    gate_path = REPO_ROOT / "scripts" / "verify_unified_lifecycle_fsm_integrity.py"
    spec = importlib.util.spec_from_file_location("_ul_fsm_gate", gate_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_GATE = _load_gate()
find_errors = _GATE.find_errors
_reachable_from = _GATE._reachable_from


class UnifiedLifecycleFsmIntegrityTests(SimpleTestCase):
    def setUp(self):
        self.valid_stage_values = {
            choice[0] for choice in SchoolLifecycleStage.Stage.choices
        }

    def test_live_fsm_is_coherent(self):
        """The shipped FSM must pass its own integrity gate with zero findings."""
        errors = find_errors(ul, self.valid_stage_values)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_every_state_has_transition_entry(self):
        self.assertEqual(
            set(ul.ALL_UNIFIED_STATES), set(ul._ALLOWED_TRANSITIONS.keys())
        )

    def test_terminal_state_is_terminal(self):
        self.assertEqual(ul._ALLOWED_TRANSITIONS[ul.STATE_PURGED], frozenset())

    def test_all_states_reachable_from_draft(self):
        reachable = _reachable_from(ul.STATE_DRAFT, ul._ALLOWED_TRANSITIONS)
        self.assertEqual(set(ul.ALL_UNIFIED_STATES), reachable)

    def test_spine_map_only_exempts_draft(self):
        mapped = set(ul.UNIFIED_STATE_TO_SPINE_STAGE.keys())
        unmapped = set(ul.ALL_UNIFIED_STATES) - mapped
        self.assertEqual(unmapped, {ul.STATE_DRAFT})

    def test_spine_map_values_are_valid_stages(self):
        for state, stage in ul.UNIFIED_STATE_TO_SPINE_STAGE.items():
            self.assertIn(stage, self.valid_stage_values, state)

    # --- the gate catches injected drift (each invariant fails loudly) ---

    def test_gate_flags_state_without_transition_entry(self):
        broken = _FakeUl(
            states=ul.ALL_UNIFIED_STATES + ("suspended",),
            transitions=ul._ALLOWED_TRANSITIONS,
            spine_map={**ul.UNIFIED_STATE_TO_SPINE_STAGE, "suspended": "OPERATING"},
        )
        errors = find_errors(broken, self.valid_stage_values)
        self.assertTrue(any("NO _ALLOWED_TRANSITIONS entry" in e for e in errors))

    def test_gate_flags_typoed_transition_target(self):
        bad_transitions = dict(ul._ALLOWED_TRANSITIONS)
        bad_transitions[ul.STATE_DRAFT] = frozenset({"provisionign"})  # typo
        broken = _FakeUl(
            states=ul.ALL_UNIFIED_STATES,
            transitions=bad_transitions,
            spine_map=ul.UNIFIED_STATE_TO_SPINE_STAGE,
        )
        errors = find_errors(broken, self.valid_stage_values)
        self.assertTrue(any("not a declared unified state" in e for e in errors))

    def test_gate_flags_missing_spine_mapping(self):
        incomplete = dict(ul.UNIFIED_STATE_TO_SPINE_STAGE)
        incomplete.pop(ul.STATE_LIVE)
        broken = _FakeUl(
            states=ul.ALL_UNIFIED_STATES,
            transitions=ul._ALLOWED_TRANSITIONS,
            spine_map=incomplete,
        )
        errors = find_errors(broken, self.valid_stage_values)
        self.assertTrue(any("no UNIFIED_STATE_TO_SPINE_STAGE mapping" in e for e in errors))

    def test_gate_flags_invalid_spine_stage_value(self):
        bad_map = {**ul.UNIFIED_STATE_TO_SPINE_STAGE, ul.STATE_LIVE: "NOT_A_STAGE"}
        broken = _FakeUl(
            states=ul.ALL_UNIFIED_STATES,
            transitions=ul._ALLOWED_TRANSITIONS,
            spine_map=bad_map,
        )
        errors = find_errors(broken, self.valid_stage_values)
        self.assertTrue(any("not a valid" in e for e in errors))


class _FakeUl:
    """Minimal stand-in exposing the three tables find_errors() reads."""

    def __init__(self, *, states, transitions, spine_map):
        self.ALL_UNIFIED_STATES = tuple(states)
        self._ALLOWED_TRANSITIONS = transitions
        self.UNIFIED_STATE_TO_SPINE_STAGE = spine_map
        self.STATE_DRAFT = ul.STATE_DRAFT
        self.STATE_PURGED = ul.STATE_PURGED
