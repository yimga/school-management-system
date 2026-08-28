"""The reference-school seeder must survive a school that already has a year.

Every school has an active AcademicYear -- onboarding creates one -- and it is
almost never named "2025/2026". ``_ensure_academic_year`` used
``get_or_create(school=..., name=...)``, so against a real tenant it added a
SECOND active year and died on ``uniq_active_academicyear_per_school``
(UNIQUE on school_id WHERE is_active). Both schools in the dev database failed
this way on 2026-08-28, which made the documented runbook
``python manage.py seed_buea_synthetic --school=<slug>`` a command that cannot
be run.

The constraint is correct and stays: ``AcademicYear.clean()`` says "Only one
academic year can be active for a school." The seeder now stands the incumbent
down instead of colliding with it.
"""

from __future__ import annotations

from datetime import date

from django.test import TestCase

from apps.academics.management.commands.seed_buea_synthetic import (
    YEAR_2526,
    Command,
)
from apps.academics.models import AcademicYear
from apps.schools.models import School


class SeedBueaAcademicYearTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # The test database ships one seeded school; make our own so the
        # incumbent year is one this test controls.
        cls.school = School.objects.create(
            name="Buea Seed Probe",
            slug="buea-seed-probe",
            subdomain="buea-seed-probe",
        )

    def _seeder(self):
        command = Command()
        command.school = self.school
        return command

    def test_stands_down_a_differently_named_active_year(self):
        incumbent = AcademicYear.objects.create(
            school=self.school,
            name="2023/2024",
            start_date=date(2023, 9, 1),
            end_date=date(2024, 7, 31),
            is_active=True,
        )

        year = self._seeder()._ensure_academic_year(
            YEAR_2526, date(2025, 9, 1), date(2026, 7, 31), active=True
        )

        incumbent.refresh_from_db()
        self.assertFalse(
            incumbent.is_active,
            "the incumbent active year must be stood down, not collided with",
        )
        self.assertTrue(year.is_active)
        self.assertEqual(
            AcademicYear.objects.filter(school=self.school, is_active=True).count(),
            1,
            "uniq_active_academicyear_per_school allows exactly one",
        )

    def test_is_idempotent(self):
        seeder = self._seeder()
        first = seeder._ensure_academic_year(
            YEAR_2526, date(2025, 9, 1), date(2026, 7, 31), active=True
        )
        second = seeder._ensure_academic_year(
            YEAR_2526, date(2025, 9, 1), date(2026, 7, 31), active=True
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            AcademicYear.objects.filter(school=self.school, is_active=True).count(), 1
        )

    def test_an_inactive_year_does_not_disturb_the_active_one(self):
        active = self._seeder()._ensure_academic_year(
            YEAR_2526, date(2025, 9, 1), date(2026, 7, 31), active=True
        )
        self._seeder()._ensure_academic_year(
            "2024/2025", date(2024, 9, 1), date(2025, 7, 31), active=False
        )
        active.refresh_from_db()
        self.assertTrue(
            active.is_active,
            "seeding a PRIOR year must not stand down the current one",
        )
        self.assertEqual(AcademicYear.objects.filter(school=self.school).count(), 2)
