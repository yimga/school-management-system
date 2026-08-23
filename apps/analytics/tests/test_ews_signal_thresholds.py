"""The RiskFactor -> StudentAtRiskSignal mirror must honour per-tenant bands.

A tenant that moved its amber cut-off away from the platform default got a
dashboard that paints a student Amber while the EWS list stayed empty (or the
reverse), because the receiver compared against a hardcoded 50.0.
"""

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.analytics.models import RiskFactor, RiskThresholds, StudentAtRiskSignal
from apps.people.models import StudentProfile
from apps.schools.models import School

User = get_user_model()


class EwsSignalHonoursTenantThresholdsTests(TestCase):
    def _school_with_thresholds(self, amber_min, red_min=80):
        uid = uuid.uuid4().hex[:10]
        school = School.objects.create(
            name=f"Band School {uid}",
            slug=f"band-{uid}",
            subdomain=f"band-{uid}",
        )
        RiskThresholds.objects.create(
            school=school, amber_min=amber_min, red_min=red_min
        )
        return school

    def _linked_student(self, school):
        uid = uuid.uuid4().hex[:8]
        user = User.objects.create_user(
            username=f"stu-{uid}", email=f"stu-{uid}@t.test", password="x"
        )
        student = StudentProfile.objects.create(
            school=school,
            user=user,
            first_name="B",
            last_name="Student",
            student_code=f"sc-{uuid.uuid4().hex[:12]}",
            admission_number=f"ad-{uuid.uuid4().hex[:12]}",
        )
        return user, student

    def test_low_amber_cutoff_still_opens_an_ews_signal(self):
        school = self._school_with_thresholds(amber_min=35)
        user, student = self._linked_student(school)

        rf = RiskFactor.objects.create(
            school=school, student=student, score=40, reason_summary="Attendance dip"
        )
        # Guard against a vacuous pass: the mirror only matters because the
        # dashboard already calls this student Amber at the tenant's own bands.
        self.assertEqual(rf.band, "amber")
        self.assertIsNotNone(student.user_id)

        self.assertTrue(
            StudentAtRiskSignal.objects.filter(
                school=school, student_user=user
            ).exists(),
            "student is Amber on this tenant's bands but no EWS signal was opened",
        )

    def test_high_amber_cutoff_does_not_open_a_signal_for_a_green_student(self):
        school = self._school_with_thresholds(amber_min=70)
        user, student = self._linked_student(school)

        rf = RiskFactor.objects.create(
            school=school, student=student, score=60, reason_summary="Minor dip"
        )
        self.assertEqual(rf.band, "green")

        self.assertFalse(
            StudentAtRiskSignal.objects.filter(
                school=school, student_user=user
            ).exists(),
            "student is Green on this tenant's bands but an EWS signal was opened",
        )

    def test_platform_default_bands_still_apply_without_a_thresholds_row(self):
        uid = uuid.uuid4().hex[:10]
        school = School.objects.create(
            name=f"Default School {uid}",
            slug=f"dflt-{uid}",
            subdomain=f"dflt-{uid}",
        )
        self.assertFalse(RiskThresholds.objects.filter(school=school).exists())
        user, student = self._linked_student(school)

        RiskFactor.objects.create(
            school=school, student=student, score=40, reason_summary="x"
        )
        self.assertFalse(
            StudentAtRiskSignal.objects.filter(school=school).exists()
        )
        RiskFactor.objects.create(
            school=school, student=student, score=72, reason_summary="y"
        )
        self.assertTrue(
            StudentAtRiskSignal.objects.filter(
                school=school, student_user=user
            ).exists()
        )
