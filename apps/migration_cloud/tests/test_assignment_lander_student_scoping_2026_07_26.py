"""Assignment landers resolve the student SCHOOL-SCOPED (no cross-school attach).

cafeteria / hostel / transport / athletics_memberships landers resolved the
student with a bare ``StudentProfile.objects.filter(**{student_lookup: external_id})``
— unscoped by school. On single-schema (RLS) deployments a same-external-id
student from ANOTHER school resolves (the inter-school-transfer hazard), so a
meal-plan balance (money), hostel bed, bus seat, or team membership could attach
to the WRONG school's student. All four now route through the canonical
school-scoping ``resolve_student`` helper, like every history lander.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from django.test import TestCase

from apps.migration_cloud.landers import _helpers
from apps.migration_cloud.landers._helpers import resolve_student
from apps.people.models import StudentProfile
from apps.schools.models import School

_LANDERS = (
    "cafeteria_assignment",
    "hostel_assignment",
    "transport_assignment",
    "athletics_memberships",
)
_LANDER_DIR = Path(_helpers.__file__).parent


class ResolveStudentScopingTests(TestCase):
    def test_same_external_id_resolves_within_its_own_school(self):
        a = School.objects.create(
            name="RS A", slug="rs-a", subdomain="rs-a", is_active=True, country_code="CM"
        )
        b = School.objects.create(
            name="RS B", slug="rs-b", subdomain="rs-b", is_active=True, country_code="CM"
        )
        sa = StudentProfile.objects.create(
            school=a, first_name="Aa", last_name="Aa", admission_number="SHARED-1"
        )
        sb = StudentProfile.objects.create(
            school=b, first_name="Bb", last_name="Bb", admission_number="SHARED-1"
        )
        got_a = resolve_student(
            ctx=SimpleNamespace(school=a), student_model=StudentProfile,
            lookup_field="admission_number", external_id="SHARED-1",
        )
        got_b = resolve_student(
            ctx=SimpleNamespace(school=b), student_model=StudentProfile,
            lookup_field="admission_number", external_id="SHARED-1",
        )
        self.assertEqual(got_a.pk, sa.pk)
        self.assertEqual(got_b.pk, sb.pk)  # NEVER school A's student


class AssignmentLanderScopingRegressionTests(TestCase):
    def test_assignment_landers_route_through_resolve_student(self):
        # The bug pattern was a bare, school-unscoped StudentProfile lookup.
        unscoped = re.compile(r"StudentProfile\.objects\.filter\(\s*\*\*\{\s*student_lookup")
        for name in _LANDERS:
            src = (_LANDER_DIR / f"{name}_lander.py").read_text(encoding="utf-8")
            self.assertIn("resolve_student", src, f"{name}: must use resolve_student")
            self.assertIsNone(
                unscoped.search(src),
                f"{name}: still resolves the student UNSCOPED via StudentProfile.objects.filter",
            )
