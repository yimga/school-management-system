"""Regression seal: lifecycle restore() must re-activate the soft-deleted school.

Bug (2026-06-17 gap analysis): mark_deleted() set both deleted_at and is_active=False,
but restore() only cleared deleted_at — leaving the "restored" tenant is_active=False and
therefore unroutable (every tenant-host path filters is_active=True). Fix re-sets
is_active=True in restore().
"""
from django.test import TestCase

from apps.lifecycle import services_offboarding
from apps.schools.models import School


class RestoreReactivatesSealTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Restore Seal School",
            slug="restore-seal",
            subdomain="restore-seal",
            is_active=True,
        )

    def test_restore_reactivates(self):
        services_offboarding.mark_deleted(self.school, reason="test")
        self.school.refresh_from_db()
        self.assertIsNotNone(self.school.deleted_at)
        self.assertFalse(self.school.is_active)

        services_offboarding.restore(self.school)
        self.school.refresh_from_db()
        self.assertIsNone(self.school.deleted_at)
        self.assertTrue(self.school.is_active, "restored school must be routable again")
