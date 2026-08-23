"""``Classroom.code`` and ``Specialty.code`` must be unique PER SCHOOL, not globally.

``Department.code`` was moved off a global unique in migration 0076 for exactly this
reason, with the reasoning written into the model. ``Classroom`` and ``Specialty``
sit in the same file and were missed.

WHY A GLOBAL UNIQUE IS WRONG HERE. ``apps.academics`` is in TENANT_APPS, so under
``USE_DJANGO_TENANTS=1`` every tenant gets its own schema and a global unique is
harmless. The sovereign edge runs ``USE_DJANGO_TENANTS=0`` with row-level security:
ONE schema, every school's rows in one table -- which is what
``0029_enable_rls_postgresql`` and ``0038_rls_policy_default_deny`` exist to separate.
A unique INDEX is not RLS-filtered, so on that deployment school B simply cannot
create a classroom whose code school A already used, and the failure surfaces as an
IntegrityError that also reveals another tenant holds the code.

The workarounds this forced are still in the tree and are the real damage:
``apps/api/oneroster_writes.py`` silently rewrites an incoming course code to
``<school-slug>-<code>`` when the bare code is taken by anyone, so a district roster
import lands MATH101 as ``westside-MATH101`` for the second school to import it.

This is a strict LOOSENING -- every row satisfying the old global unique also
satisfies (school, code) -- so it applies cleanly to existing data.
"""

from __future__ import annotations

import datetime
import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.schools.models import School


def _school(tag):
    # A blank subdomain is itself a value and the column is unique, so a second
    # School.objects.create() with no subdomain crashes. Always pass a distinct one.
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(name=f"School {slug}", slug=slug, subdomain=slug)


class CodeUniquenessIsScopedToSchoolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = _school("code-a")
        cls.b = _school("code-b")
        cls.years = {}
        cls.depts = {}
        for tag, school in (("a", cls.a), ("b", cls.b)):
            cls.years[tag] = AcademicYear.objects.create(
                school=school,
                name=f"2026/2027-{tag}",
                start_date=datetime.date(2026, 9, 1),
                end_date=datetime.date(2027, 7, 1),
            )
            cls.depts[tag] = Department.objects.create(
                school=school, name=f"General {tag}", code=f"GEN-{tag.upper()}"
            )

    def _classroom(self, tag, code):
        return Classroom.objects.create(
            school=getattr(self, tag),
            academic_year=self.years[tag],
            department=self.depts[tag],
            name=f"Class {code} {tag}",
            code=code,
        )

    def _specialty(self, tag, code):
        return Specialty.objects.create(
            school=getattr(self, tag),
            department=self.depts[tag],
            name=f"Spec {code} {tag}",
            code=code,
        )

    # ---- the two schools are genuinely distinct rows in one table -------------
    def test_the_fixture_really_is_two_schools(self):
        # Calibration. If both helpers wrote to the same school, "no collision"
        # would prove nothing at all.
        self.assertNotEqual(self.a.pk, self.b.pk)
        self.assertNotEqual(self.depts["a"].pk, self.depts["b"].pk)

    # ---- classroom -----------------------------------------------------------
    def test_two_schools_may_share_a_classroom_code(self):
        first = self._classroom("a", "F1A")
        second = self._classroom("b", "F1A")
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(Classroom.objects.filter(code="F1A").count(), 2)

    def test_one_school_still_may_not_reuse_a_classroom_code(self):
        """Loosening across schools must not become no uniqueness at all."""
        self._classroom("a", "F2A")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Classroom.objects.create(
                    school=self.a,
                    academic_year=self.years["a"],
                    department=self.depts["a"],
                    name="Duplicate",
                    code="F2A",
                )

    # ---- specialty -----------------------------------------------------------
    def test_two_schools_may_share_a_specialty_code(self):
        first = self._specialty("a", "SCI")
        second = self._specialty("b", "SCI")
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(Specialty.objects.filter(code="SCI").count(), 2)

    def test_one_school_still_may_not_reuse_a_specialty_code(self):
        self._specialty("a", "ARTS")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Specialty.objects.create(
                    school=self.a,
                    department=self.depts["a"],
                    name="Duplicate",
                    code="ARTS",
                )
