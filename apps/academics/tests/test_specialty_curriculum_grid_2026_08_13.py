"""Increment (g) — specialty↔subject curriculum + student-driven per-trade grid.

The platform had no curriculum graph and built the teaching grid only under the
single "General" specialty, so a student on a TVET trade had no matching
SubjectAssignment and — because Evaluation.clean requires
student.specialty == assignment.specialty — was ungradeable (no marks, no report
card). These tests pin: the SpecialtySubject curriculum seeds + is admin-trimmable,
and provision_per_specialty_grid gives every enrolled (classroom, specialty) pair
its assignments so a trade student is gradeable.
"""

from __future__ import annotations

from django.test import TestCase

from apps.academics.models import (
    Classroom,
    Department,
    Specialty,
    SpecialtySubject,
    Subject,
    SubjectAssignment,
)
from apps.academics.structure_provisioning import (
    ensure_academic_year,
    ensure_specialty_curriculum,
    ensure_terms,
    provision_per_specialty_grid,
    resolve_specialty_subjects,
)
from apps.people.models import StudentProfile
from apps.schools.models import School


def _trade_setup(subdomain):
    school = School.objects.create(name="TV", subdomain=subdomain, country_code="CM")
    year, _ = ensure_academic_year(school, name="2025/2026")
    ensure_terms(school, year)
    sid = str(school.id)[:6]
    dept = Department.objects.create(school=school, name="Mech", code=f"m-{sid}")
    spec = Specialty.objects.create(school=school, department=dept, name="Welding", code=f"w-{sid}")
    classroom = Classroom.objects.create(
        school=school, academic_year=year, department=dept, name="Form One", code=f"f1-{sid}"
    )
    math = Subject.objects.create(school=school, name="Mathematics")
    phys = Subject.objects.create(school=school, name="Physics")
    # A student ON the trade specialty (not General), placed in the classroom.
    student = StudentProfile.objects.create(school=school, first_name="T", last_name="S")
    StudentProfile.objects.filter(pk=student.pk).update(
        academic_year=year, classroom=classroom, specialty=spec
    )
    return school, year, dept, spec, classroom, math, phys


class CurriculumTests(TestCase):
    def test_curriculum_seeds_and_is_idempotent(self):
        school, year, dept, spec, classroom, math, phys = _trade_setup("g-curr")
        result = ensure_specialty_curriculum(school)
        # 2 subjects × (Welding) specialty = 2 links (General not present here).
        self.assertEqual(result.get("created_links"), 2)
        self.assertEqual(SpecialtySubject.objects.filter(school=school).count(), 2)
        # Idempotent.
        again = ensure_specialty_curriculum(school)
        self.assertEqual(again.get("created_links"), 0)

    def test_resolve_uses_curriculum_then_falls_back_to_all(self):
        school, year, dept, spec, classroom, math, phys = _trade_setup("g-res")
        # No links yet → fallback to ALL subjects.
        self.assertEqual(len(resolve_specialty_subjects(school, spec)), 2)
        # Link only Math → curriculum wins (Physics excluded).
        SpecialtySubject.objects.create(school=school, specialty=spec, subject=math)
        names = {s.name for s in resolve_specialty_subjects(school, spec)}
        self.assertEqual(names, {"Mathematics"})


class PerSpecialtyGridTests(TestCase):
    def test_trade_student_gets_matching_assignments(self):
        school, year, dept, spec, classroom, math, phys = _trade_setup("g-grid")
        result = provision_per_specialty_grid(school, academic_year=year)
        self.assertGreater(result.get("created_assignments", 0), 0)
        # The precise gap that blocked report cards: an assignment matching the
        # student's (classroom, specialty, year) now exists.
        self.assertTrue(
            SubjectAssignment.objects.filter(
                school=school, classroom=classroom, specialty=spec, academic_year=year
            ).exists(),
            "trade student's (classroom, specialty) must have assignments",
        )
        # It is on the trade specialty, NOT General — Evaluation.clean's
        # specialty-equality check would pass for this student.
        assignment = SubjectAssignment.objects.filter(
            school=school, classroom=classroom, specialty=spec
        ).first()
        self.assertEqual(assignment.specialty_id, spec.id)

    def test_grid_honours_curriculum_when_present(self):
        school, year, dept, spec, classroom, math, phys = _trade_setup("g-gridcurr")
        SpecialtySubject.objects.create(school=school, specialty=spec, subject=math)
        provision_per_specialty_grid(school, academic_year=year)
        subjects_assigned = set(
            SubjectAssignment.objects.filter(school=school, specialty=spec)
            .values_list("subject__name", flat=True)
        )
        self.assertIn("Mathematics", subjects_assigned)
        self.assertNotIn("Physics", subjects_assigned)  # not in the curriculum

    def test_no_enrolled_pairs_is_a_graceful_skip(self):
        school = School.objects.create(name="Empty", subdomain="g-empty", country_code="CM")
        year, _ = ensure_academic_year(school, name="2025/2026")
        ensure_terms(school, year)
        result = provision_per_specialty_grid(school, academic_year=year)
        self.assertEqual(result.get("skipped"), "no_enrolled_pairs")
