"""G5 — the single-tenant-era gilead-school seed must not live as an active husk.

``schools/0012`` get_or_creates ``gilead-school`` is_active=True on every fresh
database. Migration 0079 retires it: an UNPROVISIONED husk is flipped inactive,
but a gilead-school that was genuinely provisioned (``phase_a_complete``) is left
strictly alone -- deactivating a real tenant would be worse than the husk.
"""
from __future__ import annotations

import importlib

from django.apps import apps as django_apps
from django.test import TestCase

from apps.schools.models import School

_MIGRATION = importlib.import_module(
    "apps.schools.migrations.0079_retire_gilead_school_husk"
)


class RetireGileadSchoolHuskTests(TestCase):
    def _seed(self, *, is_active: bool, settings: dict | None = None) -> School:
        obj, _ = School.objects.update_or_create(
            slug="gilead-school",
            defaults={
                "name": "Gilead School System Management System",
                "subdomain": "gilead-school",
                "is_active": is_active,
                "settings": settings or {},
            },
        )
        return obj

    def test_seeded_gilead_school_is_retired_after_migrations(self):
        # The migration ran when the test DB was built (or was applied by keepdb):
        # the seeded row must already be inactive.
        seeded = School.objects.filter(slug="gilead-school").first()
        self.assertIsNotNone(
            seeded, "schools/0012 seeds gilead-school into every database"
        )
        self.assertFalse(
            seeded.is_active,
            "migration 0079 must retire the seeded unprovisioned husk",
        )

    def test_unprovisioned_husk_is_deactivated(self):
        self._seed(is_active=True, settings={})
        _MIGRATION.retire_legacy_husk(django_apps, None)
        self.assertFalse(
            School.objects.get(slug="gilead-school").is_active,
            "an active gilead-school with no phase_a_complete marker is a husk",
        )

    def test_provisioned_gilead_school_is_left_active(self):
        self._seed(
            is_active=True,
            settings={"provisioning": {"phase_a_complete": True}},
        )
        _MIGRATION.retire_legacy_husk(django_apps, None)
        self.assertTrue(
            School.objects.get(slug="gilead-school").is_active,
            "a genuinely provisioned gilead-school is a real tenant, not a husk -- "
            "the migration must never deactivate it",
        )

    def test_reverse_is_a_noop(self):
        # Reverse must not resurrect the husk it retired.
        self._seed(is_active=False, settings={})
        _MIGRATION.noop_reverse(django_apps, None)
        self.assertFalse(School.objects.get(slug="gilead-school").is_active)
