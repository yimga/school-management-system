"""A tenant provisioning calls COMPLETED must be able to run a school day.

Found by an A-Z lifecycle audit (2026-07-16) — the headline finding, and the one
no gate could have caught: nothing was broken, nothing raised, and every step
reported SUCCESS. The tenant was simply EMPTY where it mattered.

At ``phase_b_complete=True`` provisioning created zero Specialty and zero
SubjectAssignment. Both are load-bearing:

  * ``SubjectAssignment`` is the hinge the school day turns on — teachers reach
    classrooms through ``TeacherAssignment -> subject_assignment__classroom_id``
    (portal/views_teacher.py) and marks point at a SubjectAssignment
    (evals/views.py). With none, a day-1 teacher opened the classroom dropdown
    and saw NOTHING: no attendance, no grade entry, and no error to explain it.
    An empty dropdown reads as "no data yet", not "your tenant is broken".

  * ``FeePlan.specialty`` is a non-null FK, so with no Specialty no fee plan
    could exist at all — and the automated fee task returns
    ``{"status": "no_plans"}`` as SUCCESS (finance/tasks.py), so the failure was
    invisible from the operator side too.

These tests assert the tenant is USABLE, not merely that provisioning finished.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.schools.models import School


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class ProvisionedTenantIsUsableTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Usable Academy",
            slug="usable-academy",
            subdomain="usable-academy",
            country_code="CM",
            is_active=False,
        )
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(self.school.id), contact_email="owner@usable.test")

    def test_a_default_specialty_exists(self):
        self.assertTrue(
            Specialty.objects.filter(school=self.school).exists(),
            "no Specialty means FeePlan (non-null specialty FK) can never be "
            "created -- the school cannot bill anyone",
        )

    def test_specialty_code_is_namespaced_per_school(self):
        """Specialty.code is GLOBALLY unique -- a shared code breaks school #2."""
        other = School.objects.create(
            name="Second Academy",
            slug="second-academy",
            subdomain="second-academy",
            country_code="CM",
            is_active=False,
        )
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(other.id), contact_email="owner@second.test")

        codes = set(
            Specialty.objects.filter(school__in=[self.school, other]).values_list(
                "code", flat=True
            )
        )
        self.assertEqual(
            len(codes),
            Specialty.objects.filter(school__in=[self.school, other]).count(),
            "two schools must not share a Specialty code -- the second school's "
            "provisioning would die on a UNIQUE violation",
        )

    def test_the_teaching_grid_is_seeded(self):
        self.assertTrue(
            SubjectAssignment.objects.filter(school=self.school).exists(),
            "zero SubjectAssignments means a day-1 teacher sees an empty "
            "classroom dropdown: no attendance, no grade entry, no error",
        )

    def test_grid_covers_every_classroom_and_subject_for_the_active_term(self):
        year = AcademicYear.objects.filter(school=self.school, is_active=True).first()
        self.assertIsNotNone(year)
        term = Term.objects.filter(
            school=self.school, academic_year=year, is_active=True
        ).first()
        self.assertIsNotNone(term, "the year must have an active term")

        classrooms = Classroom.objects.filter(school=self.school, academic_year=year)
        subjects = Subject.objects.filter(school=self.school)
        self.assertGreater(classrooms.count(), 0)
        self.assertGreater(subjects.count(), 0)

        self.assertEqual(
            SubjectAssignment.objects.filter(
                school=self.school, academic_year=year, term=term
            ).count(),
            classrooms.count() * subjects.count(),
            "every classroom must be teachable in every subject for the term",
        )

    def test_every_grid_row_is_reachable_from_a_classroom(self):
        """The exact join the teacher portal makes."""
        classroom_ids = set(
            SubjectAssignment.objects.filter(school=self.school).values_list(
                "classroom_id", flat=True
            )
        )
        self.assertEqual(
            classroom_ids,
            set(
                Classroom.objects.filter(school=self.school).values_list(
                    "id", flat=True
                )
            ),
            "a classroom absent from the grid is invisible to every teacher",
        )

    def test_no_third_term_row_on_a_classroom_that_forbids_it(self):
        """SubjectAssignment.clean() rejects these; create() never calls clean()."""
        offending = SubjectAssignment.objects.filter(
            school=self.school,
            term__position=3,
            classroom__allows_third_term=False,
        )
        self.assertEqual(
            offending.count(),
            0,
            "the seed must honour the third-term rule the model enforces, rather "
            "than writing rows the model itself considers invalid",
        )

    def test_reseeding_the_grid_is_idempotent(self):
        from apps.academics.structure_provisioning import (
            provision_teaching_grid_for_school,
        )

        before = SubjectAssignment.objects.filter(school=self.school).count()
        result = provision_teaching_grid_for_school(self.school)
        self.assertEqual(result.get("created_assignments"), 0)
        self.assertEqual(
            SubjectAssignment.objects.filter(school=self.school).count(), before
        )

    def test_grid_completes_after_a_partial_seed(self):
        """A resume must finish a grid a killed drive left half-built."""
        from apps.academics.structure_provisioning import (
            provision_teaching_grid_for_school,
        )

        full = SubjectAssignment.objects.filter(school=self.school).count()
        self.assertGreater(full, 1)
        survivor = SubjectAssignment.objects.filter(school=self.school).first()
        SubjectAssignment.objects.filter(school=self.school).exclude(
            pk=survivor.pk
        ).delete()

        provision_teaching_grid_for_school(self.school)

        self.assertEqual(
            SubjectAssignment.objects.filter(school=self.school).count(),
            full,
            "the grid seed must complete a partial grid",
        )

    def test_owner_progress_strip_reports_the_grid_step(self):
        from apps.schools.provisioning_progress import resolve_provisioning_progress

        payload = resolve_provisioning_progress(self.school)
        keys = {s.get("key") for s in payload.get("extended_steps") or []}
        self.assertIn(
            "teaching_grid",
            keys,
            "a real seeded step must be visible to the owner, not silent",
        )


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class TeachingGridPrerequisitesTests(TestCase):
    """The seed must degrade honestly, never half-write or raise."""

    def test_missing_prerequisites_is_reported_not_raised(self):
        from apps.academics.structure_provisioning import (
            provision_teaching_grid_for_school,
        )

        school = School.objects.create(
            name="Bare Academy",
            slug="bare-academy",
            subdomain="bare-academy",
            is_active=False,
        )
        result = provision_teaching_grid_for_school(school)
        self.assertEqual(result.get("created_assignments"), 0)
        self.assertTrue(result.get("skipped"))
