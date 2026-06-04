"""DB-level validation of the offline person-create idempotency constraints.

These exercise the partial UniqueConstraints added in people/0057 (Wave 3b of
the 2026-06-04 remediation). The handler-level dedup is covered by SimpleTestCase
suites; this asserts the *database* actually refuses a duplicate so a concurrent
two-device replay cannot create twins, while blank client_offline_id rows (the
online-create path) stay exempt.
"""
from __future__ import annotations

import itertools

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.people.models import Applicant, StudentProfile, TeacherProfile
from apps.schools.models import School

User = get_user_model()


class OfflineIdempotencyConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Offline Idem School",
            slug="offline-idem-school",
            subdomain="offline-idem-school",
            is_active=True,
        )
        cls.other_school = School.objects.create(
            name="Offline Idem Other",
            slug="offline-idem-other",
            subdomain="offline-idem-other",
            is_active=True,
        )

    def setUp(self):
        self._user_seq = itertools.count(1)

    def _new_user(self):
        n = next(self._user_seq)
        return User.objects.create(
            username=f"teacher-idem-{id(self)}-{n}",
            email=f"teacher-idem-{id(self)}-{n}@example.test",
        )

    # ---- StudentProfile ----
    def _student(self, key, school):
        return StudentProfile.objects.create(
            school=school, first_name="S", last_name="X", client_offline_id=key
        )

    def test_student_duplicate_offline_id_rejected(self):
        self._student("dev-key-1", self.school)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._student("dev-key-1", self.school)

    def test_student_blank_offline_id_exempt(self):
        self._student("", self.school)
        self._student("", self.school)  # no raise — online path

    def test_student_cross_school_same_key_ok(self):
        self._student("shared-key", self.school)
        self._student("shared-key", self.other_school)  # different tenant

    # ---- TeacherProfile (requires a User) ----
    def _teacher(self, key, school):
        return TeacherProfile.objects.create(
            school=school, user=self._new_user(), client_offline_id=key
        )

    def test_teacher_duplicate_offline_id_rejected(self):
        self._teacher("dev-key-1", self.school)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._teacher("dev-key-1", self.school)

    def test_teacher_blank_offline_id_exempt(self):
        self._teacher("", self.school)
        self._teacher("", self.school)

    # ---- Applicant (email required) ----
    def _applicant(self, key, school):
        return Applicant.objects.create(
            school=school,
            first_name="A",
            last_name="X",
            email="applicant-idem@example.test",
            client_offline_id=key,
        )

    def test_applicant_duplicate_offline_id_rejected(self):
        self._applicant("dev-key-1", self.school)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._applicant("dev-key-1", self.school)

    def test_applicant_blank_offline_id_exempt(self):
        self._applicant("", self.school)
        self._applicant("", self.school)
