"""Tests for the settlement state machine — pure logic, no DB."""

from __future__ import annotations

import unittest

from apps.marketplace.settlement_state_machine import (
    IllegalSettlementTransition,
    assert_legal_transition,
    is_legal_transition,
    legal_next_phases,
)
from apps.marketplace.settlement_truth import (
    PHASE_OTHER,
    PHASE_SETTLEMENT_EXTERNAL_BLOCKED,
    PHASE_SETTLEMENT_FAILED,
    PHASE_SETTLEMENT_PAID,
    PHASE_SETTLEMENT_PENDING,
    PHASE_SETTLEMENT_READY,
    PHASE_SETTLEMENT_RECONCILED,
)


class SettlementStateMachineTests(unittest.TestCase):
    def test_pending_to_paid_legal(self):
        self.assertTrue(is_legal_transition(PHASE_SETTLEMENT_PENDING, PHASE_SETTLEMENT_PAID))

    def test_paid_to_reconciled_legal(self):
        self.assertTrue(is_legal_transition(PHASE_SETTLEMENT_PAID, PHASE_SETTLEMENT_RECONCILED))

    def test_failed_is_sink(self):
        self.assertEqual(legal_next_phases(PHASE_SETTLEMENT_FAILED), [])

    def test_reconciled_is_sink(self):
        self.assertEqual(legal_next_phases(PHASE_SETTLEMENT_RECONCILED), [])

    def test_paid_back_to_pending_illegal(self):
        self.assertFalse(is_legal_transition(PHASE_SETTLEMENT_PAID, PHASE_SETTLEMENT_PENDING))

    def test_reconciled_back_to_paid_illegal(self):
        self.assertFalse(is_legal_transition(PHASE_SETTLEMENT_RECONCILED, PHASE_SETTLEMENT_PAID))

    def test_external_blocked_recovery_legal(self):
        self.assertTrue(
            is_legal_transition(PHASE_SETTLEMENT_EXTERNAL_BLOCKED, PHASE_SETTLEMENT_READY)
        )

    def test_self_transition_allowed_for_idempotency(self):
        self.assertTrue(is_legal_transition(PHASE_SETTLEMENT_PAID, PHASE_SETTLEMENT_PAID))

    def test_assert_raises_on_illegal(self):
        with self.assertRaises(IllegalSettlementTransition):
            assert_legal_transition(PHASE_SETTLEMENT_PAID, PHASE_SETTLEMENT_PENDING)

    def test_assert_passes_on_legal(self):
        # Should not raise.
        assert_legal_transition(PHASE_SETTLEMENT_PENDING, PHASE_SETTLEMENT_READY)

    def test_unknown_from_phase_treated_as_other(self):
        # Unknown phase still allows entry into pending / external_blocked.
        self.assertTrue(is_legal_transition("unknown_phase", PHASE_SETTLEMENT_PENDING))

    def test_pending_to_reconciled_illegal_must_go_through_paid(self):
        self.assertFalse(
            is_legal_transition(PHASE_SETTLEMENT_PENDING, PHASE_SETTLEMENT_RECONCILED)
        )

    def test_other_to_paid_illegal_no_skip(self):
        self.assertFalse(is_legal_transition(PHASE_OTHER, PHASE_SETTLEMENT_PAID))


if __name__ == "__main__":
    unittest.main()
