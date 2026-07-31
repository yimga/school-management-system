"""Blueprint → module (School.features) bridge tests.

Applying a blueprint should switch on the opt-in modules its archetype explicitly
names (boarding → dormitory, low-connectivity → offline_mode), enable nothing for a
core-only blueprint (no fabrication), only ever enable real registry codes, and honor
the optional entitlement gate.
"""
from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.blueprint_contract import get_blueprint
from apps.platform_runtime.blueprint_modules import (
    enable_blueprint_modules,
    resolve_blueprint_feature_codes,
)
from apps.schools.feature_registry import FEATURE_REGISTRY


class _StubSchool:
    """Minimal School stand-in: just enough surface for enable_blueprint_modules."""

    def __init__(self, features=None):
        self.features = dict(features or {})
        self.saved_fields = None

    def save(self, update_fields=None):
        self.saved_fields = list(update_fields or [])


class ResolveBlueprintFeatureCodesTests(TestCase):
    def test_boarding_school_implies_dormitory_and_parent_chat(self):
        codes = resolve_blueprint_feature_codes(get_blueprint("boarding-school"))
        # boarding-school modules: Hostel, Attendance, Discipline, Fees, Communication
        self.assertIn("dormitory", codes)  # Hostel -> dormitory
        self.assertIn("parent_chat", codes)  # Communication -> parent_chat

    def test_low_connectivity_school_implies_offline_mode(self):
        codes = resolve_blueprint_feature_codes(get_blueprint("low-connectivity-school"))
        self.assertIn("offline_mode", codes)  # Offline sync -> offline_mode

    def test_core_only_blueprint_fabricates_nothing(self):
        # multi-campus-network modules: Group analytics, Tenant lifecycle, Billing, Support
        # — all core/operator surfaces, none of which map to a toggleable module code.
        codes = resolve_blueprint_feature_codes(get_blueprint("multi-campus-network"))
        self.assertEqual(codes, [])

    def test_only_real_registry_codes_are_returned(self):
        registry_codes = {m["code"] for m in FEATURE_REGISTRY}
        for key in (
            "private-primary-school",
            "private-secondary-school",
            "boarding-school",
            "low-connectivity-school",
            "cameroon-gce-school",
            "bilingual-school",
            "international-school",
        ):
            for code in resolve_blueprint_feature_codes(get_blueprint(key)):
                self.assertIn(code, registry_codes)


class EnableBlueprintModulesTests(TestCase):
    def test_persist_false_reports_without_saving(self):
        school = _StubSchool()
        res = enable_blueprint_modules(school, get_blueprint("boarding-school"), persist=False)
        self.assertIn("dormitory", res["enabled"])
        # persist=False must not mutate/save the school
        self.assertEqual(school.features, {})
        self.assertIsNone(school.saved_fields)

    def test_persist_true_sets_features_and_saves(self):
        school = _StubSchool()
        res = enable_blueprint_modules(school, get_blueprint("boarding-school"), persist=True)
        self.assertTrue(school.features.get("dormitory"))
        self.assertTrue(school.features.get("parent_chat"))
        self.assertEqual(school.saved_fields, ["features", "updated_at"])
        self.assertIn("dormitory", res["enabled"])

    def test_already_enabled_reported_not_reenabled(self):
        school = _StubSchool(features={"dormitory": True})
        res = enable_blueprint_modules(school, get_blueprint("boarding-school"), persist=True)
        self.assertIn("dormitory", res["already_on"])
        self.assertNotIn("dormitory", res["enabled"])

    def test_entitlement_gate_skips_unentitled_codes(self):
        school = _StubSchool()
        res = enable_blueprint_modules(
            school,
            get_blueprint("boarding-school"),
            persist=True,
            entitled_codes={"parent_chat"},
        )
        # dormitory is resolved but not entitled -> skipped, never granted
        self.assertIn("dormitory", res["skipped_unentitled"])
        self.assertFalse(school.features.get("dormitory"))
        # parent_chat is entitled -> enabled
        self.assertIn("parent_chat", res["enabled"])
        self.assertTrue(school.features.get("parent_chat"))

    def test_core_only_blueprint_enables_nothing(self):
        school = _StubSchool()
        res = enable_blueprint_modules(school, get_blueprint("multi-campus-network"), persist=True)
        self.assertEqual(res["enabled"], [])
        self.assertEqual(school.features, {})
        self.assertIsNone(school.saved_fields)

    def test_none_school_or_blueprint_is_safe(self):
        self.assertEqual(enable_blueprint_modules(None, get_blueprint("boarding-school"))["resolved"], [])
        self.assertEqual(enable_blueprint_modules(_StubSchool(), None)["resolved"], [])
