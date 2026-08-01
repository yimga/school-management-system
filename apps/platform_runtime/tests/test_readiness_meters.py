"""Honest readiness meters compute real values (no hardcoded placeholders).

These are pure-function unit tests (no DB) that lock the behaviour the
setup-meter placeholders (72/70/74) never had: the bar reaches 100 exactly
when every concrete check is satisfied, drops for each unmet fact, and reports
*which* facts are unmet so the caption can explain the shortfall.
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.platform_runtime.readiness_meters import (
    ReadinessCheck,
    blueprint_readiness,
    blueprint_readiness_checks,
    pack_readiness,
    readiness_from_checks,
)


class ReadinessFromChecksTests(SimpleTestCase):
    def test_all_satisfied_is_100(self):
        checks = [ReadinessCheck(40, True, "a"), ReadinessCheck(60, True, "b")]
        self.assertEqual(readiness_from_checks(checks), 100)

    def test_none_satisfied_is_0(self):
        checks = [ReadinessCheck(40, False, "a"), ReadinessCheck(60, False, "b")]
        self.assertEqual(readiness_from_checks(checks), 0)

    def test_weighted_partial(self):
        checks = [ReadinessCheck(40, True, "a"), ReadinessCheck(60, False, "b")]
        self.assertEqual(readiness_from_checks(checks), 40)

    def test_fractional_credit(self):
        checks = [ReadinessCheck(100, 0.5, "half")]
        self.assertEqual(readiness_from_checks(checks), 50)

    def test_empty_is_0_not_crash(self):
        self.assertEqual(readiness_from_checks([]), 0)


class BlueprintReadinessTests(SimpleTestCase):
    def _preview(self, **overrides):
        base = {
            "can_apply": True,
            "conflicts": [],
            "external_required": [],
            "offline_readiness": {"status": "READY"},
        }
        base.update(overrides)
        return base

    def test_fully_ready_non_payment_blueprint_reaches_100(self):
        result = blueprint_readiness(self._preview())
        self.assertEqual(result["value"], 100)
        self.assertTrue(result["complete"])
        self.assertEqual(result["unmet"], [])

    def test_payment_blueprint_honestly_caps_below_100_with_reason(self):
        # A payment-capable blueprint that is otherwise fully applyable reads 85
        # for a tenant that has neither a live rail nor a recorded posture — and
        # it names the remaining go-live work.
        result = blueprint_readiness(
            self._preview(external_required=["live_payment_collection"])
        )
        self.assertEqual(result["value"], 85)
        self.assertFalse(result["complete"])
        self.assertIn("Live payment onboarding", result["unmet"])

    def test_live_rail_satisfies_the_payment_check(self):
        with patch(
            "apps.finance.fee_collection_posture.resolve_live_collection_state",
            return_value={
                "live": True,
                "not_applicable": False,
                "label": "Live collection enabled",
            },
        ):
            result = blueprint_readiness(
                self._preview(external_required=["live_payment_collection"]),
                school=object(),
            )

        self.assertEqual(result["value"], 100)
        self.assertTrue(result["complete"])

    def test_recorded_manual_posture_drops_the_check_from_the_weighting(self):
        # Not-applicable ≠ credited: the check leaves the list entirely, so the
        # score is taken over the checks that DO apply to this tenant. A tenant
        # that reconciles fees by hand is not 15% short of anything.
        with patch(
            "apps.finance.fee_collection_posture.resolve_live_collection_state",
            return_value={
                "live": False,
                "not_applicable": True,
                "label": "Manual reconciliation posture recorded",
            },
        ):
            preview = self._preview(external_required=["live_payment_collection"])
            checks = blueprint_readiness_checks(preview, school=object())
            result = blueprint_readiness(preview, school=object())

        self.assertEqual([check.label for check in checks],
                         ["Applyable preview", "Conflict-free", "Offline proof"])
        self.assertEqual(result["value"], 100)
        self.assertEqual(result["unmet"], [])

    def test_resolver_failure_never_fabricates_a_pass(self):
        with patch(
            "apps.finance.fee_collection_posture.resolve_live_collection_state",
            side_effect=RuntimeError("db down"),
        ):
            result = blueprint_readiness(
                self._preview(external_required=["live_payment_collection"]),
                school=object(),
            )

        self.assertEqual(result["value"], 85)
        self.assertIn("Live payment onboarding", result["unmet"])

    def test_composite_offline_status_is_not_counted_as_ready(self):
        # Must-fire seal on the inverted meter: the retired composite status was
        # emitted BECAUSE of a payment blocker and scored as offline-ready, so a
        # payment-gated blueprint out-scored a clean one. If it ever comes back,
        # it must not earn the offline weight.
        result = blueprint_readiness(
            self._preview(offline_readiness={"status": "READY_WITH_EXTERNAL_BLOCKERS"})
        )

        self.assertIn("Offline proof", result["unmet"])
        # 40 + 25 of an 85-point applicable total (no payment gate declared here,
        # so its 15 is not in the denominator at all).
        self.assertEqual(result["value"], 76)

    def test_blocked_preview_scores_low(self):
        result = blueprint_readiness(
            self._preview(
                can_apply=False,
                conflicts=[{"code": "tenant_required"}],
                offline_readiness={"status": "PARTIAL"},
            )
        )
        # Nothing satisfied and no payment gate declared → the three applicable
        # checks (40 + 25 + 20) are all unmet.
        self.assertEqual(result["value"], 0)
        self.assertFalse(result["complete"])


class PackReadinessTests(SimpleTestCase):
    def test_ready_pack_reaches_100(self):
        preview = {"can_apply": True, "conflicts": [], "external_required": []}
        self.assertEqual(pack_readiness(preview)["value"], 100)

    def test_pack_with_conflict_drops(self):
        preview = {"can_apply": True, "conflicts": [{"code": "x"}], "external_required": []}
        result = pack_readiness(preview)
        self.assertEqual(result["value"], 70)  # 50 apply + 20 deps, conflict (30) unmet
        self.assertIn("Conflict-free", result["unmet"])
