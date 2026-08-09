"""Seals for the onboarding-waiver primitive (2026-08-09).

A school with no data to migrate must be able to WAIVE that decision durably,
auditable, and reversibly — and the two waiver kinds (migration vs roster) must
stay independent so "no legacy data" never silently implies "launch empty".

These tests FAIL before apps/schools/onboarding_waiver.py exists / behaves.
"""
from __future__ import annotations

from django.test import TestCase

from apps.schools.models import School
from apps.schools import onboarding_waiver as ow


class OnboardingWaiverPrimitiveTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Fresh Start Academy",
            slug="fresh-start",
            subdomain="fresh-start",
            is_active=True,
            country_code="CM",
        )

    def _reload(self):
        return School.objects.get(pk=self.school.pk)

    def test_defaults_to_not_waived(self):
        self.assertFalse(ow.migration_waived(self.school))
        self.assertFalse(ow.roster_waived(self.school))
        self.assertEqual(ow.get_waiver(self.school, ow.WAIVER_MIGRATION), {})

    def test_waive_migration_is_durable_and_audited(self):
        ow.waive(
            self.school,
            ow.WAIVER_MIGRATION,
            actor=None,
            reason=ow.REASON_NO_LEGACY_DATA,
            note="Brand-new school, starting fresh.",
        )
        # Durable: survives a reload from the DB.
        reloaded = self._reload()
        self.assertTrue(ow.migration_waived(reloaded))
        rec = ow.get_waiver(reloaded, ow.WAIVER_MIGRATION)
        self.assertEqual(rec["state"], ow.STATE_WAIVED)
        self.assertEqual(rec["reason"], ow.REASON_NO_LEGACY_DATA)
        self.assertEqual(rec["note"], "Brand-new school, starting fresh.")
        self.assertIn("waived_at", rec)
        # Auditable: a history entry was recorded.
        self.assertEqual(len(rec["history"]), 1)
        self.assertEqual(rec["history"][0]["state"], ow.STATE_WAIVED)

    def test_migration_waiver_does_not_imply_roster_waiver(self):
        ow.waive(self.school, ow.WAIVER_MIGRATION, reason=ow.REASON_NO_LEGACY_DATA)
        reloaded = self._reload()
        self.assertTrue(ow.migration_waived(reloaded))
        # The roster decision is independent — a school with no legacy data still
        # enters its current roster natively.
        self.assertFalse(ow.roster_waived(reloaded))

    def test_unwaive_is_reversible_and_keeps_history(self):
        ow.waive(self.school, ow.WAIVER_MIGRATION, reason=ow.REASON_NO_LEGACY_DATA)
        ow.unwaive(self._reload(), ow.WAIVER_MIGRATION)
        reloaded = self._reload()
        self.assertFalse(ow.migration_waived(reloaded))
        rec = ow.get_waiver(reloaded, ow.WAIVER_MIGRATION)
        self.assertEqual(rec["state"], ow.STATE_ACTIVE)
        self.assertIn("restored_at", rec)
        # Full trail preserved: waive then un-waive = 2 history entries.
        self.assertEqual([h["state"] for h in rec["history"]],
                         [ow.STATE_WAIVED, ow.STATE_ACTIVE])

    def test_roster_waiver_independent_round_trip(self):
        ow.waive(self.school, ow.WAIVER_ROSTER, reason=ow.REASON_NO_STUDENTS_YET)
        reloaded = self._reload()
        self.assertTrue(ow.roster_waived(reloaded))
        self.assertFalse(ow.migration_waived(reloaded))

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            ow.waive(self.school, "not_a_kind")
