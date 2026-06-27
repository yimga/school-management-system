"""Unit tests for the pure payment-corridor risk-tier helpers.

No DB access: ``apps.finance.payment_risk_tier`` is a set of frozensets +
two pure functions returning a frozen dataclass. The existing
``test_regional_payment_profiles_local_global_contract`` suite calls
``evaluate_risk`` once on a normalized profile, but never covers
``default_risk_tier_for_country`` directly, the no-profile branch, the
invalid-tier coercion, or the counsel-blocked permission gating. These
assertions lock that pure decision logic.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.finance.payment_risk_tier import (
    ALLOWED_RISK_TIERS,
    HIGH_RISK_ISO2,
    RISK_COUNSEL_BLOCKED,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    RiskDecision,
    default_risk_tier_for_country,
    evaluate_risk,
)


class DefaultRiskTierForCountryTests(SimpleTestCase):
    def test_high_risk_countries_resolve_high(self):
        for iso2 in ("NG", "GH", "KE", "ZA", "IN"):
            self.assertEqual(default_risk_tier_for_country(iso2), RISK_HIGH, iso2)

    def test_unlisted_country_defaults_to_medium(self):
        self.assertEqual(default_risk_tier_for_country("FR"), RISK_MEDIUM)
        self.assertEqual(default_risk_tier_for_country("CA"), RISK_MEDIUM)

    def test_empty_or_none_defaults_to_medium(self):
        self.assertEqual(default_risk_tier_for_country(""), RISK_MEDIUM)
        self.assertEqual(default_risk_tier_for_country(None), RISK_MEDIUM)

    def test_case_insensitive_and_whitespace_tolerant(self):
        self.assertEqual(default_risk_tier_for_country(" ng "), RISK_HIGH)

    def test_only_first_two_chars_considered(self):
        # The function slices to the first 2 chars before lookup.
        self.assertEqual(default_risk_tier_for_country("NGA"), RISK_HIGH)

    def test_high_risk_set_membership_is_consistent(self):
        for iso2 in HIGH_RISK_ISO2:
            self.assertEqual(default_risk_tier_for_country(iso2), RISK_HIGH, iso2)


class EvaluateRiskTests(SimpleTestCase):
    def test_no_profile_returns_medium_with_safe_permissions(self):
        decision = evaluate_risk(None)
        self.assertIsInstance(decision, RiskDecision)
        self.assertEqual(decision.tier, RISK_MEDIUM)
        self.assertEqual(decision.reason, "no_regional_profile")
        self.assertTrue(decision.allow_live_charge)
        self.assertFalse(decision.allow_split_payout)
        self.assertTrue(decision.allow_connect_onboarding)

    def test_empty_profile_dict_treated_as_no_profile(self):
        self.assertEqual(evaluate_risk({}).tier, RISK_MEDIUM)
        self.assertEqual(evaluate_risk({}).reason, "no_regional_profile")

    def test_explicit_risk_tier_is_honored(self):
        decision = evaluate_risk({"risk_tier": RISK_LOW})
        self.assertEqual(decision.tier, RISK_LOW)
        # Only low-risk corridors may run split payouts.
        self.assertTrue(decision.allow_split_payout)

    def test_tier_derived_from_country_when_absent(self):
        decision = evaluate_risk({"country_code": "NG"})
        self.assertEqual(decision.tier, RISK_HIGH)
        self.assertFalse(decision.allow_split_payout)

    def test_invalid_tier_coerced_to_medium(self):
        decision = evaluate_risk({"risk_tier": "not_a_real_tier"})
        self.assertEqual(decision.tier, RISK_MEDIUM)
        self.assertIn(decision.tier, ALLOWED_RISK_TIERS)

    def test_counsel_blocked_disables_all_money_actions(self):
        decision = evaluate_risk({"risk_tier": RISK_COUNSEL_BLOCKED})
        self.assertEqual(decision.tier, RISK_COUNSEL_BLOCKED)
        self.assertFalse(decision.allow_live_charge)
        self.assertFalse(decision.allow_split_payout)
        self.assertFalse(decision.allow_connect_onboarding)

    def test_custom_reason_is_passed_through(self):
        decision = evaluate_risk({"risk_tier": RISK_HIGH, "risk_reason": "manual_review"})
        self.assertEqual(decision.reason, "manual_review")

    def test_default_reason_includes_resolved_tier(self):
        decision = evaluate_risk({"risk_tier": RISK_HIGH})
        self.assertEqual(decision.reason, "profile_risk_high")

    def test_decision_is_frozen_dataclass(self):
        decision = evaluate_risk({"risk_tier": RISK_LOW})
        with self.assertRaises(Exception):
            decision.tier = RISK_HIGH  # type: ignore[misc]
