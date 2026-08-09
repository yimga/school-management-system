"""Seals for the up-front signup "no data to migrate" declaration (2026-08-09).

The public onboarding migration step now offers a DISTINCT "We have no data to
migrate" choice that is a durable WAIVE, kept separate from "Set up migration
later" which is a defer (must NOT waive). The choice rides a session flag and is
recorded once the school exists.

These tests FAIL before the signup flow distinguishes waive from defer.
"""
from __future__ import annotations

from django.test import Client, TestCase
from django.urls import reverse

from apps.schools.models import School
from apps.schools import onboarding_waiver as ow


class WaiveMigrationIfFlaggedTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Fresh Signup School",
            slug="fresh-signup",
            subdomain="fresh-signup",
            is_active=True,
            country_code="CM",
        )

    def _fresh(self):
        return School.objects.get(pk=self.school.pk)

    def test_flag_true_records_durable_migration_waiver(self):
        ow.waive_migration_if_flagged(self.school, True)
        rec = ow.get_waiver(self._fresh(), ow.WAIVER_MIGRATION)
        self.assertTrue(ow.migration_waived(self._fresh()))
        self.assertEqual(rec["reason"], ow.REASON_NO_LEGACY_DATA)

    def test_flag_false_is_a_noop_defer(self):
        ow.waive_migration_if_flagged(self.school, False)
        self.assertFalse(ow.migration_waived(self._fresh()))
        self.assertEqual(
            ow.get_waiver(self._fresh(), ow.WAIVER_MIGRATION), {}
        )

    def test_flag_none_is_a_noop(self):
        ow.waive_migration_if_flagged(self.school, None)
        self.assertFalse(ow.migration_waived(self._fresh()))


class OnboardWizardMigrationStepTests(TestCase):
    def _post_step3(self, data):
        client = Client()
        payload = {"step": "3", **data}
        resp = client.post(reverse("onboard_wizard") + "?step=3", payload)
        return resp, client

    def test_no_data_choice_sets_the_waive_flag(self):
        resp, client = self._post_step3({"no_data_to_migrate": "1"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(client.session.get("onboarding_migration_waived"))
        # It also clears any vendor (nothing to migrate).
        self.assertIsNone(client.session.get("onboarding_migrate_vendor"))

    def test_set_up_later_is_defer_not_waive(self):
        resp, client = self._post_step3({"skip_migration": "1"})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(client.session.get("onboarding_migration_waived"))
