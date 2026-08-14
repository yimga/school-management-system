"""Increment (c) — the country subject catalog reaches the migration path.

A roster-only export lands students but no subjects, so the teaching grid stayed
empty (missing_prerequisites) and no report card could be produced — even though
signup already seeds a country subject catalog. ``seed_country_subjects`` (now
called inside ``provision_country_baseline``) brings the two doors to parity:

* a school with NO subjects gets its country/education-system default catalog;
* an uploaded catalog is never touched;
* once subjects + a classroom + terms exist, the grid actually populates.
"""

from __future__ import annotations

from django.test import TestCase

from apps.academics.models import Classroom, Subject, SubjectAssignment
from apps.academics.structure_provisioning import (
    ensure_academic_year,
    ensure_general_department,
    provision_country_baseline,
    seed_country_subjects,
)
from apps.schools.models import School


class SubjectCatalogSeedTests(TestCase):
    def test_bare_school_gets_the_country_subject_catalog(self):
        school = School.objects.create(name="Bare", subdomain="bare-subj", country_code="CM")
        self.assertEqual(Subject.objects.filter(school=school).count(), 0)

        result = seed_country_subjects(school)
        self.assertGreater(result.get("created_subjects", 0), 0)
        self.assertGreater(Subject.objects.filter(school=school).count(), 0)
        # A recognizable academic subject lands (CM pack → Mathematics; fallback →
        # Math/Mathematics). Case/spelling-robust.
        self.assertTrue(
            Subject.objects.filter(school=school, name__icontains="math").exists(),
            "a mathematics subject should be seeded",
        )

    def test_existing_catalog_is_never_overridden(self):
        school = School.objects.create(name="HasCat", subdomain="has-cat", country_code="CM")
        Subject.objects.create(school=school, name="Welding Theory")

        result = seed_country_subjects(school)
        self.assertEqual(result.get("skipped"), "catalog_exists")
        # Only the uploaded subject remains — the seed did not add academic subjects
        # on top of a school that already declared its own catalog.
        self.assertEqual(Subject.objects.filter(school=school).count(), 1)
        self.assertEqual(Subject.objects.filter(school=school).first().name, "Welding Theory")

    def test_grid_populates_after_subjects_and_classroom_exist(self):
        school = School.objects.create(name="Grid", subdomain="grid-subj", country_code="CM")
        year, _ = ensure_academic_year(school, name="2025/2026")
        # A classroom the grid can hang assignments on (the roster/structure engine
        # creates these for K-12 sectors; we make one explicitly to isolate the
        # subjects→grid chain).
        Classroom.objects.create(
            school=school, academic_year=year, department=ensure_general_department(school),
            name="Form One", code=f"grid-{str(school.id)[:8]}-f1",
        )
        summary = provision_country_baseline(school, academic_year=year)

        self.assertGreater(summary.get("subjects", {}).get("created_subjects", 0), 0)
        self.assertGreater(
            SubjectAssignment.objects.filter(school=school, academic_year=year).count(), 0,
            "with subjects + a classroom + terms, the teaching grid must populate",
        )
