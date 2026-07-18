"""Honest readiness meters compute real values (no hardcoded placeholders).

These are pure-function unit tests (no DB) that lock the behaviour the
setup-meter placeholders (72/70/74) never had: the bar reaches 100 exactly
when every concrete check is satisfied, drops for each unmet fact, and reports
*which* facts are unmet so the caption can explain the shortfall.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.readiness_meters import (
    ReadinessCheck,
    blueprint_readiness,
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
        # A payment-capable blueprint that is otherwise fully applyable reads 85,
        # not a fake 72 — and it names the remaining go-live work.
        result = blueprint_readiness(
            self._preview(
                external_required=["live_payment_collection"],
                offline_readiness={"status": "READY_WITH_EXTERNAL_BLOCKERS"},
            )
        )
        self.assertEqual(result["value"], 85)
        self.assertFalse(result["complete"])
        self.assertIn("Live payment onboarding", result["unmet"])

    def test_blocked_preview_scores_low(self):
        result = blueprint_readiness(
            self._preview(
                can_apply=False,
                conflicts=[{"code": "tenant_required"}],
                offline_readiness={"status": "PARTIAL"},
            )
        )
        # 40 (apply) + 25 (conflict-free) + 20 (offline) all unmet → only the
        # external check (15) can be satisfied here.
        self.assertEqual(result["value"], 15)
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
