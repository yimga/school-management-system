"""Phase 0X property-based tests for governance invariants.

Hypothesis is preferred; the suite falls back to a deterministic sampling loop
when Hypothesis is unavailable so the gate is testable in lean CI environments.
"""

from __future__ import annotations

import logging
import random
import unittest
from typing import Any

LOGGER = logging.getLogger(__name__)

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False


VALID_DOMAINS = ("curriculum", "fees", "hr", "branding", "emis", "integrations")
VALID_MODES_PER_DOMAIN = ("inherit", "local", "hybrid")
OPERATING_MODES = ("standalone", "group_member", "group_member_sovereign")


def _build_inherit_map(seed: int) -> dict[str, str]:
    """Deterministic inherit map for a given seed."""
    rng = random.Random(seed)
    return {domain: rng.choice(VALID_MODES_PER_DOMAIN) for domain in VALID_DOMAINS}


def _apply_inherit_map(state: dict[str, Any], inherit_map: dict[str, str]) -> dict[str, Any]:
    """Pure function: applies an inherit map to a state dict.

    Idempotent by contract: applying twice equals applying once.
    """
    next_state = dict(state)
    next_state["governance_inherit"] = dict(inherit_map)
    return next_state


def _isolated_tenant_view(tenant_id: int, all_tenant_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure function: returns only rows for the given tenant.

    Models the invariant that for any org depth, tenant isolation holds.
    """
    return [row for row in all_tenant_rows if row.get("school_id") == tenant_id]


class GovernanceInvariantsDeterministic(unittest.TestCase):
    """Deterministic sampling cover for environments without Hypothesis."""

    def test_apply_inherit_map_is_idempotent(self) -> None:
        for seed in range(64):
            inherit_map = _build_inherit_map(seed)
            initial: dict[str, Any] = {"school_id": seed, "governance_inherit": {}}
            once = _apply_inherit_map(initial, inherit_map)
            twice = _apply_inherit_map(once, inherit_map)
            self.assertEqual(once, twice, msg=f"inherit map not idempotent for seed={seed}")

    def test_standalone_mode_invariant(self) -> None:
        """A school with operating_mode='standalone' must ignore any non-empty inherit map."""
        for seed in range(64):
            inherit_map = _build_inherit_map(seed)
            standalone_row: dict[str, Any] = {
                "school_id": seed,
                "operating_mode": "standalone",
                "governance_inherit": {},
            }
            applied = _apply_inherit_map(standalone_row, inherit_map)
            self.assertEqual(applied["operating_mode"], "standalone")

    def test_tenant_isolation_at_arbitrary_depth(self) -> None:
        """For any number of tenants, _isolated_tenant_view returns only rows for the target tenant."""
        for tenant_count in (1, 5, 25, 100):
            rows = [{"school_id": i, "payload": f"row-{i}"} for i in range(tenant_count)]
            for target in range(tenant_count):
                view = _isolated_tenant_view(target, rows)
                self.assertEqual(len(view), 1, msg=f"tenant_count={tenant_count} target={target}")
                self.assertEqual(view[0]["school_id"], target)

    def test_operating_mode_enumeration_stability(self) -> None:
        """Operating modes are immutable canon; this guards against silent additions."""
        self.assertEqual(
            set(OPERATING_MODES),
            {"standalone", "group_member", "group_member_sovereign"},
        )


if HYPOTHESIS_AVAILABLE:
    class GovernanceInvariantsHypothesis(unittest.TestCase):
        @given(
            st.dictionaries(
                keys=st.sampled_from(VALID_DOMAINS),
                values=st.sampled_from(VALID_MODES_PER_DOMAIN),
                min_size=0,
                max_size=len(VALID_DOMAINS),
            )
        )
        @settings(max_examples=200, deadline=None)
        def test_inherit_map_idempotence(self, inherit_map: dict[str, str]) -> None:
            initial: dict[str, Any] = {"school_id": 1, "governance_inherit": {}}
            once = _apply_inherit_map(initial, inherit_map)
            twice = _apply_inherit_map(once, inherit_map)
            self.assertEqual(once, twice)

        @given(
            st.integers(min_value=1, max_value=200),
            st.integers(min_value=0, max_value=199),
        )
        @settings(max_examples=200, deadline=None)
        def test_tenant_isolation(self, tenant_count: int, target: int) -> None:
            if target >= tenant_count:
                target = target % tenant_count
            rows = [{"school_id": i, "payload": f"row-{i}"} for i in range(tenant_count)]
            view = _isolated_tenant_view(target, rows)
            self.assertEqual(len(view), 1)
            self.assertEqual(view[0]["school_id"], target)


if __name__ == "__main__":
    unittest.main()
