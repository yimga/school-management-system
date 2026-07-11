"""Regression tests for the 2026-07-11 lander-completeness fix.

Before this wave the ``staff``/``finance``/``sections`` landers wrote to fields
their target models don't have and never set required FKs, so every row
quarantined and the imported count was pinned to 0 (silent data loss on every
import path — connector wizard, companion bundle, customer intake). The
``academics`` domain had no lander at all, so courses landed as opaque DFV blobs
instead of ``Subject`` rows. These tests lock the "lands a real row" contract
edge by edge — the DoD is ``created > 0`` with zero silent quarantine.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Subject
from apps.finance.models import Invoice
from apps.migration_cloud.landers.academics_lander import AcademicsLander
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.finance_lander import FinanceLander
from apps.migration_cloud.landers.sections_lander import SectionsLander
from apps.migration_cloud.landers.staff_lander import StaffLander
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School

User = get_user_model()


def _ctx(school, dry_run=False) -> LanderContext:
    return LanderContext(
        school=school, schema_name="", bundle_id=None, artifact_id=None, dry_run=dry_run
    )


class StaffLanderCompletenessTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Staff Co", slug="staff-co", subdomain="staff-co")

    def _row(self, **o):
        row = {
            "staff_external_id": "EMP-1",
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "role": "Teacher",
            "department": "Science",
        }
        row.update(o)
        return row

    def test_provisions_user_and_teacher_profile(self):
        result = StaffLander().land(canonical_rows=iter([self._row()]), ctx=_ctx(self.school))
        self.assertEqual(result.quarantined, 0, result.errors)
        self.assertEqual(result.created, 1)
        profile = TeacherProfile.objects.get(staff_id="EMP-1")
        self.assertIsNotNone(profile.user_id)  # the REQUIRED OneToOne is set
        self.assertEqual(profile.school_id, self.school.pk)
        self.assertEqual(profile.user.email, "jane@example.com")
        self.assertFalse(profile.user.has_usable_password())

    def test_rerun_is_idempotent(self):
        lander, ctx = StaffLander(), _ctx(self.school)
        lander.land(canonical_rows=iter([self._row()]), ctx=ctx)
        lander.land(canonical_rows=iter([self._row(role="Head of Science")]), ctx=ctx)
        self.assertEqual(TeacherProfile.objects.filter(staff_id="EMP-1").count(), 1)

    def test_student_role_is_never_provisioned_as_teacher(self):
        # A combined OneRoster users.csv is pre-classified to staff but carries
        # every role; a student row must be skipped, never made a teacher.
        result = StaffLander().land(
            canonical_rows=iter([self._row(staff_external_id="STU-9", role="student")]),
            ctx=_ctx(self.school),
        )
        self.assertEqual(result.created, 0)
        self.assertEqual(result.skipped, 1)
        self.assertFalse(TeacherProfile.objects.filter(staff_id="STU-9").exists())


class FinanceLanderCompletenessTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Fin Co", slug="fin-co", subdomain="fin-co")
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Pay", last_name="Er", admission_number="ADM-f-1"
        )

    def _row(self, **o):
        row = {
            "student_external_id": "ADM-f-1",
            "reference": "INV-1",
            "amount": "1250.00",
            "due_date": "2025-09-30",
            "issue_date": "2025-09-01",
            "description": "Tuition Q1",
        }
        row.update(o)
        return row

    def test_lands_invoice_with_amount_profile_and_notes(self):
        result = FinanceLander().land(canonical_rows=iter([self._row()]), ctx=_ctx(self.school))
        self.assertEqual(result.quarantined, 0, result.errors)
        self.assertEqual(result.created, 1)
        inv = Invoice.objects.get(reference="INV-1")
        self.assertEqual(inv.total_amount, Decimal("1250.00"))  # NOT the 0.00 default
        self.assertIsNotNone(inv.profile_id)  # required PROTECT FK is set
        self.assertEqual(inv.student_id, self.student.pk)
        self.assertEqual(inv.notes, "Tuition Q1")
        self.assertEqual(inv.issued_date, date(2025, 9, 1))

    def test_rerun_is_idempotent(self):
        lander, ctx = FinanceLander(), _ctx(self.school)
        lander.land(canonical_rows=iter([self._row()]), ctx=ctx)
        lander.land(canonical_rows=iter([self._row(amount="1300.00")]), ctx=ctx)
        self.assertEqual(Invoice.objects.filter(reference="INV-1").count(), 1)


class SectionsLanderCompletenessTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Sec Co", slug="sec-co", subdomain="sec-co")

    def _row(self, **o):
        row = {
            "section_code": "MATH-7A",
            "name": "Mathematics Grade 7 A",
            "academic_year": "2025-2026",
            "grade_level": "7",
        }
        row.update(o)
        return row

    def test_lands_classroom_with_required_fks_and_minted_code(self):
        result = SectionsLander().land(canonical_rows=iter([self._row()]), ctx=_ctx(self.school))
        self.assertEqual(result.quarantined, 0, result.errors)
        self.assertEqual(result.created, 1)
        cls = Classroom.objects.get(school=self.school, name="Mathematics Grade 7 A")
        self.assertIsNotNone(cls.academic_year_id)  # required PROTECT FK
        self.assertIsNotNone(cls.department_id)      # required PROTECT FK
        self.assertNotEqual(cls.code, "MATH-7A")     # code is minted, not the source's global code
        AcademicYear.objects.get(school=self.school, name="2025-2026")

    def test_does_not_overwrite_another_schools_classroom_on_code_collision(self):
        # Single-schema hazard: the source code must never resolve/rename a
        # different school's classroom (Classroom.code is globally unique).
        other = School.objects.create(name="Other", slug="other-sec", subdomain="other-sec")
        SectionsLander().land(canonical_rows=iter([self._row()]), ctx=_ctx(other))
        other_cls = Classroom.objects.get(school=other)
        SectionsLander().land(canonical_rows=iter([self._row()]), ctx=_ctx(self.school))
        other_cls.refresh_from_db()
        self.assertEqual(other_cls.school_id, other.pk)  # untouched
        self.assertTrue(Classroom.objects.filter(school=self.school).exists())


class AcademicsLanderTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Acad Co", slug="acad-co", subdomain="acad-co")

    def test_courses_become_real_subject_rows(self):
        rows = [
            {"subject_code": "MATH101", "subject_name": "Mathematics"},
            {"subject_code": "ENG101", "subject_name": "English"},
        ]
        result = AcademicsLander().land(canonical_rows=iter(rows), ctx=_ctx(self.school))
        self.assertEqual(result.quarantined, 0, result.errors)
        self.assertEqual(result.created, 2)
        self.assertTrue(Subject.objects.filter(school=self.school, name="Mathematics").exists())
        self.assertTrue(Subject.objects.filter(school=self.school, name="English").exists())

    def test_rerun_is_idempotent(self):
        lander, ctx = AcademicsLander(), _ctx(self.school)
        lander.land(canonical_rows=iter([{"subject_name": "Mathematics"}]), ctx=ctx)
        result = lander.land(canonical_rows=iter([{"subject_name": "Mathematics"}]), ctx=ctx)
        self.assertEqual(result.created, 0)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(Subject.objects.filter(school=self.school, name="Mathematics").count(), 1)
