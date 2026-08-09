"""Seal: a migration waiver resolves the "Data migrated" readiness phase (2026-08-09).

Before this, school_readiness read migration_status from settings, which the
Migration Cloud pipeline never writes back — so a school that opted into a
vendor migration and then found it had no data showed a perpetually-pending
"Data migrated" phase with no way to resolve it. A migration waiver now marks
that phase done ("Not needed"), and also surfaces a resolved phase for a school
that declared "no data to migrate" up front.

These tests FAIL before school_readiness honors the migration waiver.
"""
from __future__ import annotations

from django.test import TestCase

from apps.schools.models import School
from apps.schools import onboarding_waiver as ow
from apps.schools.school_readiness import build_school_readiness


def _migrate_phase(result):
    return next((p for p in result["phases"] if p.get("key") == "migrate"), None)


class MigrateMeterWaiverTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Migrate Meter School",
            slug="migrate-meter",
            subdomain="migrate-meter",
            is_active=True,
            country_code="CM",
        )

    def _set_vendor_intent(self):
        blob = dict(self.school.settings or {})
        blob["rmc_public_onboarding"] = {
            "migration": {"vendor_slug": "powerschool", "status": "not_started"}
        }
        self.school.settings = blob
        self.school.save(update_fields=["settings"])

    def _fresh(self):
        return School.objects.get(pk=self.school.pk)

    def test_migrate_phase_pending_with_intent_and_no_data(self):
        self._set_vendor_intent()
        phase = _migrate_phase(build_school_readiness(self._fresh()))
        self.assertIsNotNone(phase)
        self.assertFalse(phase["done"])

    def test_migration_waiver_resolves_the_migrate_phase(self):
        self._set_vendor_intent()
        ow.waive(self.school, ow.WAIVER_MIGRATION, reason=ow.REASON_NO_LEGACY_DATA)
        phase = _migrate_phase(build_school_readiness(self._fresh()))
        self.assertIsNotNone(phase)
        self.assertTrue(phase["done"])
        self.assertIn("not needed", phase["detail"].lower())

    def test_waiver_without_vendor_intent_surfaces_resolved_phase(self):
        ow.waive(self.school, ow.WAIVER_MIGRATION, reason=ow.REASON_STARTING_FRESH)
        phase = _migrate_phase(build_school_readiness(self._fresh()))
        self.assertIsNotNone(phase)
        self.assertTrue(phase["done"])
