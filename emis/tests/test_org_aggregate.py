"""Phase 4D — EMIS organization aggregate pipeline tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from emis.org_aggregate import aggregate_organization_emis


class OrgEmisAggregateTests(SimpleTestCase):
    @patch("apps.schools.models.School")
    @patch("apps.people.models.TeacherProfile")
    @patch("apps.people.models.StudentProfile")
    def test_inspector_role_hides_per_school_breakdown(self, mock_student, mock_teacher, mock_school):
        org = SimpleNamespace(pk="org-1")
        school = SimpleNamespace(pk="s1", name="Alpha")
        mock_school.objects.filter.return_value = [school]
        mock_student.objects.filter.return_value.count.return_value = 120
        mock_teacher.objects.filter.return_value.count.return_value = 8

        agg = aggregate_organization_emis(org, reporter_role="inspector")
        self.assertEqual(agg.students_count, 120)
        self.assertEqual(agg.by_school, ())
        payload = agg.to_dict()
        self.assertNotIn("by_school", payload)

    @patch("apps.schools.models.School")
    @patch("apps.people.models.TeacherProfile")
    @patch("apps.people.models.StudentProfile")
    def test_owner_role_includes_school_breakdown(self, mock_student, mock_teacher, mock_school):
        org = SimpleNamespace(pk="org-1")
        school = SimpleNamespace(pk="s1", name="Alpha")
        mock_school.objects.filter.return_value = [school]

        student_qs = mock_student.objects.filter.return_value
        student_qs.count.return_value = 50
        teacher_qs = mock_teacher.objects.filter.return_value
        teacher_qs.count.return_value = 4

        agg = aggregate_organization_emis(org, reporter_role="owner")
        self.assertEqual(len(agg.by_school), 1)
        self.assertEqual(agg.by_school[0]["school_name"], "Alpha")
