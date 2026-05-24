"""SFDP Phase 3 local-global profile contract tests (batch 1452+)."""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase

from apps.finance.local_checkout_context import build_checkout_rail_cards, payment_method_choices
from apps.finance.payment_evidence_generator import evidence_paths_for_country
from apps.finance.payment_local_global_contract import (
    PHASE3_REQUIRED_FIELDS,
    REGION_DEPTH_PACKS,
    apply_phase3_enrichment,
    validate_all_profiles,
)
from apps.finance.payment_rail_taxonomy import adapter_registry_parity_findings
from apps.finance.payment_risk_tier import evaluate_risk
from apps.finance.regional_payment_profiles import clear_profile_cache, get_normalized_regional_profile

PROFILES_PATH = Path(__file__).resolve().parent.parent / "data" / "regional_payment_profiles.json"


class RegionalPaymentProfilesLocalGlobalContractTests(SimpleTestCase):
    def setUp(self):
        clear_profile_cache()

    def test_profiles_file_has_200_plus_countries(self):
        data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data), 200)

    def test_phase3_required_fields_after_normalization(self):
        for iso2 in ("NG", "BR", "IN", "AE", "FR", "CA", "CM"):
            profile = get_normalized_regional_profile(iso2)
            self.assertIsNotNone(profile)
            for field in PHASE3_REQUIRED_FIELDS:
                self.assertIn(field, profile)
                self.assertTrue(profile.get(field) not in (None, "", []))

    def test_validate_all_profiles_clean(self):
        data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
        enriched = {k: apply_phase3_enrichment(k, v) for k, v in data.items()}
        findings = validate_all_profiles(enriched)
        self.assertEqual(findings, [], msg=findings[:5])

    def test_regional_depth_packs(self):
        br = apply_phase3_enrichment("BR", {})
        self.assertEqual(br["currency"], "BRL")
        self.assertIn("PIX", br["primary_rails"])
        in_row = apply_phase3_enrichment("IN", {})
        self.assertIn("UPI", in_row["primary_rails"])

    def test_checkout_rail_cards_for_nigeria(self):
        bundle = build_checkout_rail_cards("NG")
        self.assertTrue(bundle["cards"])
        self.assertTrue(payment_method_choices("NG"))

    def test_rail_taxonomy_registry_parity(self):
        self.assertEqual(adapter_registry_parity_findings(), [])

    def test_evidence_generator_paths(self):
        paths = evidence_paths_for_country("NG")
        self.assertTrue(any("paystack" in p.get("psp_slug", "") for p in paths if "psp_slug" in p))

    def test_risk_tier_evaluate(self):
        decision = evaluate_risk(get_normalized_regional_profile("NG"))
        self.assertIn(decision.tier, {"low", "medium", "high", "counsel_blocked"})

    def test_anchor_countries_in_depth_or_enriched(self):
        for iso2 in REGION_DEPTH_PACKS:
            row = get_normalized_regional_profile(iso2)
            self.assertNotEqual(row.get("label"), iso2)
