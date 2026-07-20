"""Phase 1: post-apply verification — prove uploaded rows landed AND are visible.

reconciliation.py used to compute "parity" from the landers' OWN self-reported
counts, so a rolled-back / wrong-school apply still showed 100%. These tests lock
the new behaviour: verification re-queries the tenant (verify_landed_counts) and
the tenant results page turns source -> landed -> visible into a clear per-domain
report that flags drift when created rows are not actually present.
"""

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.migration_cloud.verification import (
    domains_with_verification,
    verify_landed_counts,
)
from apps.migration_cloud.views_tenant_upload import _build_verification


class VerifyLandedCountsTests(SimpleTestCase):
    def test_no_school_returns_empty(self):
        # No school bound → nothing to verify, never raises.
        self.assertEqual(
            verify_landed_counts(SimpleNamespace(school=None, schema_name="")), {}
        )

    def test_spec_covers_core_confirmed_domains(self):
        d = domains_with_verification()
        for expected in ("students", "staff", "guardians", "finance"):
            self.assertIn(expected, d)


class BuildVerificationTests(SimpleTestCase):
    def _bundle(self, per_domain, notes=None):
        return SimpleNamespace(
            reconciliation_summary={"per_domain": per_domain, "notes": notes or []}
        )

    def test_none_before_any_reconciliation(self):
        self.assertIsNone(_build_verification(SimpleNamespace(reconciliation_summary=None)))
        self.assertIsNone(_build_verification(SimpleNamespace(reconciliation_summary={})))

    def test_ok_when_visible_meets_created(self):
        v = _build_verification(self._bundle([
            {"domain": "students", "source_count": 100, "target_created": 100,
             "target_updated": 0, "target_visible_count": 100},
        ]))
        self.assertTrue(v["ok"])
        row = v["rows"][0]
        self.assertEqual(row["landed"], 100)
        self.assertEqual(row["visible_label"], 100)
        self.assertFalse(row["drift"])

    def test_drift_when_visible_below_created(self):
        # Landers said created=100 but only 40 are visible → the apply did not
        # persist. This must be flagged (this is exactly what the old self-report
        # parity could never catch).
        v = _build_verification(self._bundle([
            {"domain": "students", "source_count": 100, "target_created": 100,
             "target_updated": 0, "target_visible_count": 40},
        ]))
        self.assertFalse(v["ok"])
        self.assertTrue(v["rows"][0]["drift"])

    def test_unverified_domain_is_dash_not_drift(self):
        # A domain with no model mapping reports no visible count — shown as "—",
        # never mis-flagged as drift. payroll/compliance stay DFV-only.
        v = _build_verification(self._bundle([
            {"domain": "payroll", "source_count": 50, "target_created": 50,
             "target_updated": 0, "target_visible_count": None},
        ]))
        self.assertTrue(v["ok"])
        self.assertEqual(v["rows"][0]["visible_label"], "—")
        self.assertFalse(v["rows"][0]["drift"])

    def test_spec_covers_extended_domains(self):
        d = domains_with_verification()
        for expected in ("attendance", "grades", "behavior", "sections", "health"):
            self.assertIn(expected, d)
    def test_updates_only_never_drift(self):
        # created=0 (all updates) can never trip the "created not present" check.
        v = _build_verification(self._bundle([
            {"domain": "students", "source_count": 100, "target_created": 0,
             "target_updated": 100, "target_visible_count": 100},
        ]))
        self.assertTrue(v["ok"])
        self.assertEqual(v["rows"][0]["landed"], 100)
