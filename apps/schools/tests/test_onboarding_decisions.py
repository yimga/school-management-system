"""Tests for the progressive onboarding decision model.

These lock the three properties the surface promises:
  * every decision badges exactly one recommended option (single source of truth
    for what the UI pre-selects),
  * decisions the country / cycles / funding already settle are auto-applied
    (ask=False) so the tenant is not asked,
  * decisions that cannot apply for the context are dropped entirely.
Everything is pure and offline-safe, so SimpleTestCase (no DB) is enough.
"""

from django.test import SimpleTestCase

from apps.schools.onboarding_decisions import build_onboarding_decisions
from apps.schools.onboarding_recommendations import build_onboarding_recommendations


def _dim(model, key):
    return next((d for d in model["dimensions"] if d["key"] == key), None)


class DecisionModelInvariantTests(SimpleTestCase):
    def test_every_dimension_badges_exactly_one_recommended_option_that_exists(self):
        model = build_onboarding_decisions(country_code="CM", education_cycles=["secondary"])
        self.assertTrue(model["dimensions"])
        for dim in model["dimensions"]:
            flagged = [o for o in dim["options"] if o["recommended"]]
            self.assertEqual(len(flagged), 1, f"{dim['key']} must badge exactly one option")
            self.assertEqual(flagged[0]["value"], dim["recommended_value"])
            values = {o["value"] for o in dim["options"]}
            self.assertIn(dim["recommended_value"], values,
                          f"{dim['key']} recommended_value must be a real option")

    def test_offline_safe_and_deterministic_fingerprint(self):
        a = build_onboarding_decisions(country_code="NG", education_cycles=["secondary"], funding_type="mission")
        b = build_onboarding_decisions(country_code="NG", education_cycles=["secondary"], funding_type="mission")
        self.assertTrue(a["offline_safe"])
        self.assertEqual(a["fingerprint"], b["fingerprint"])

    def test_ask_and_auto_keys_partition_the_dimensions(self):
        model = build_onboarding_decisions(country_code="CM", education_cycles=["secondary"])
        keys = {d["key"] for d in model["dimensions"]}
        self.assertEqual(set(model["ask_keys"]) | set(model["auto_keys"]), keys)
        self.assertFalse(set(model["ask_keys"]) & set(model["auto_keys"]))
        # auto_applied only carries the non-asked decisions.
        self.assertEqual(set(model["auto_applied"]), set(model["auto_keys"]))


class AutoDerivationTests(SimpleTestCase):
    def test_limited_connectivity_country_is_auto_offline_first(self):
        model = build_onboarding_decisions(country_code="CM", education_cycles=["secondary"])
        conn = _dim(model, "connectivity_profile")
        self.assertEqual(conn["recommended_value"], "limited")
        self.assertFalse(conn["ask"])          # auto-applied, not asked
        self.assertTrue(str(conn["auto_reason"]))

    def test_reliable_connectivity_country_is_auto_cloud_first(self):
        model = build_onboarding_decisions(country_code="US", education_cycles=["secondary"])
        conn = _dim(model, "connectivity_profile")
        self.assertEqual(conn["recommended_value"], "reliable")
        self.assertFalse(conn["ask"])

    def test_unknown_country_falls_back_to_asking_connectivity(self):
        model = build_onboarding_decisions(country_code="XX", education_cycles=["secondary"])
        conn = _dim(model, "connectivity_profile")
        self.assertEqual(conn["recommended_value"], "mixed")
        self.assertTrue(conn["ask"])           # don't assume — ask

    def test_region_key_drives_connectivity_when_country_unknown(self):
        model = build_onboarding_decisions(
            country_code="", region_key="africa-anglophone", education_cycles=["secondary"])
        conn = _dim(model, "connectivity_profile")
        self.assertEqual(conn["recommended_value"], "limited")
        self.assertFalse(conn["ask"])

    def test_national_exam_board_auto_applied_for_public_school(self):
        model = build_onboarding_decisions(
            country_code="NG", education_cycles=["secondary"], funding_type="public")
        board = _dim(model, "curriculum_board")
        self.assertEqual(board["recommended_value"], "waec-neco")
        self.assertFalse(board["ask"])         # unambiguous for the country
        # the specific national board is surfaced as a selectable option
        self.assertIn("waec-neco", {o["value"] for o in board["options"]})

    def test_private_school_is_still_asked_the_board(self):
        model = build_onboarding_decisions(
            country_code="NG", education_cycles=["secondary"], funding_type="private")
        board = _dim(model, "curriculum_board")
        self.assertTrue(board["ask"])          # IB/Cambridge common here → ask
        self.assertIn("ib", {o["value"] for o in board["options"]})

    def test_strict_governance_auto_applied_in_regulated_jurisdiction(self):
        model = build_onboarding_decisions(country_code="GB", education_cycles=["secondary"])
        gov = _dim(model, "governance_profile")
        self.assertEqual(gov["recommended_value"], "strict")
        self.assertFalse(gov["ask"])

    def test_public_school_skips_the_fee_question(self):
        model = build_onboarding_decisions(
            country_code="KE", education_cycles=["primary"], funding_type="public")
        pay = _dim(model, "payment_profile")
        self.assertEqual(pay["recommended_value"], "basic")
        self.assertFalse(pay["ask"])

    def test_mobile_money_market_recommends_multi_channel_for_private(self):
        model = build_onboarding_decisions(
            country_code="KE", education_cycles=["secondary"], funding_type="private")
        pay = _dim(model, "payment_profile")
        self.assertEqual(pay["recommended_value"], "multi-channel")
        self.assertTrue(pay["ask"])

    def test_multi_campus_count_auto_sets_network_scope(self):
        model = build_onboarding_decisions(
            country_code="CM", education_cycles=["secondary"],
            institution_profile={"campus_count": 4})
        scope = _dim(model, "organization_scope")
        self.assertEqual(scope["recommended_value"], "network")
        self.assertFalse(scope["ask"])


class ProgressiveSkipTests(SimpleTestCase):
    def test_higher_ed_only_drops_session_and_board_questions(self):
        model = build_onboarding_decisions(country_code="CM", education_cycles=["university"])
        keys = {d["key"] for d in model["dimensions"]}
        self.assertNotIn("session_pattern", keys)
        self.assertNotIn("curriculum_board", keys)
        # governance and connectivity still apply to any institution
        self.assertIn("governance_profile", keys)
        self.assertIn("connectivity_profile", keys)

    def test_school_age_keeps_session_and_board_questions(self):
        model = build_onboarding_decisions(country_code="CM", education_cycles=["secondary"])
        keys = {d["key"] for d in model["dimensions"]}
        self.assertIn("session_pattern", keys)
        self.assertIn("curriculum_board", keys)


class ManifestConsumesNewDimensionsTests(SimpleTestCase):
    def test_new_dimensions_flow_into_recommended_modules(self):
        manifest = build_onboarding_recommendations(
            country_code="CM",
            education_cycles=["secondary"],
            institution_profile={
                "session_pattern": "double",
                "curriculum_board": "ib",
                "governance_profile": "strict",
            },
        )
        modules = manifest["recommendations"]["modules"]
        self.assertIn("multi-session-timetable", modules)
        self.assertIn("international-curriculum", modules)
        self.assertIn("compliance-governance", modules)
        self.assertEqual(manifest["recommendations"]["governance"], "strict-compliance-profile")

    def test_defaults_leave_new_modules_out(self):
        manifest = build_onboarding_recommendations(
            country_code="CM", education_cycles=["secondary"])
        modules = manifest["recommendations"]["modules"]
        self.assertNotIn("multi-session-timetable", modules)
        self.assertNotIn("international-curriculum", modules)
