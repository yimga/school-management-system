"""Compliance must count DISTINCT doses, not ImmunizationRecord rows.

``compute_missing_immunizations`` incremented a per-vaccine counter once per
row, so two rows for dose 1 — a double-submitted admin form, or a correction
entered as a new row instead of an edit — satisfied a 2-dose requirement. The
``dose_number`` column, the whole point of the W24 move off free-text
HealthRecord, was never read. The child is one dose short and the guardian is
never told.

The 1-dose-recorded-twice-for-a-1-dose-requirement case is the vacuity guard:
it pins that duplicate rows do not start manufacturing NON-compliance either,
so the fix is "count doses", not "count fewer things".
"""

from __future__ import annotations

import uuid

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.finance.models import Notification
from apps.people.models import StudentGuardian, StudentProfile
from apps.schoolops.immunization import compute_missing_immunizations
from apps.schoolops.models import ImmunizationRecord, VaccineRequirement
from apps.schools.models import School

_ALERT_TITLE = "Immunization records incomplete"


class DistinctDoseCountingTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"IMMD {uid}", slug=f"immd-{uid}", subdomain=f"immd{uid}", is_active=True
        )
        self.student = StudentProfile.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            date_of_birth="2015-01-01",
            student_code=f"S{uid}",
            school=self.school,
            is_active=True,
        )
        self.guardian = User.objects.create_user(
            username=f"guardian-{uid}", password="pass12345", role=User.Role.PARENT
        )
        StudentGuardian.objects.create(
            guardian_user=self.guardian, student=self.student, receives_sms=False
        )

    def _dose(self, dose_number):
        return ImmunizationRecord.objects.create(
            school=self.school,
            student=self.student,
            vaccine="MMR",
            dose_number=dose_number,
        )

    def _alerts(self):
        return Notification.objects.filter(
            recipient=self.guardian, title=_ALERT_TITLE
        ).count()

    def test_dose_one_recorded_twice_does_not_satisfy_a_two_dose_requirement(self):
        VaccineRequirement.objects.create(
            school=self.school, vaccine="MMR", doses_required=2
        )
        self._dose(1)
        self._dose(1)
        self.assertEqual(ImmunizationRecord.objects.count(), 2)  # both rows exist

        result = compute_missing_immunizations(self.student, self.school)
        self.assertFalse(result["is_compliant"], result)
        self.assertEqual(len(result["missing"]), 1)
        self.assertEqual(result["missing"][0]["doses_on_record"], 1)

    def test_the_sweep_alerts_the_guardian_of_the_duplicated_dose(self):
        VaccineRequirement.objects.create(
            school=self.school, vaccine="MMR", doses_required=2
        )
        self._dose(1)
        self._dose(1)

        self.assertEqual(self._alerts(), 0)
        call_command("check_missing_immunizations", school=self.school.slug)
        self.assertEqual(self._alerts(), 1)

    def test_two_distinct_doses_still_satisfy_a_two_dose_requirement(self):
        VaccineRequirement.objects.create(
            school=self.school, vaccine="MMR", doses_required=2
        )
        self._dose(1)
        self._dose(2)
        result = compute_missing_immunizations(self.student, self.school)
        self.assertTrue(result["is_compliant"], result)

    def test_duplicate_rows_do_not_manufacture_noncompliance(self):
        # Vacuity guard: a 1-dose requirement with dose 1 recorded twice is
        # still compliant — the fix must count doses, not penalise duplicates.
        VaccineRequirement.objects.create(
            school=self.school, vaccine="MMR", doses_required=1
        )
        self._dose(1)
        self._dose(1)
        result = compute_missing_immunizations(self.student, self.school)
        self.assertTrue(result["is_compliant"], result)
        call_command("check_missing_immunizations", school=self.school.slug)
        self.assertEqual(self._alerts(), 0)
