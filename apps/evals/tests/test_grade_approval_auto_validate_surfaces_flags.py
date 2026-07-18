"""The grade-approval auto-validate toggle must actually surface flags.

Found by an A-Z audit follow-up (dead-guard backlog item 10).

``create_grade_approval_request`` computed data-quality flags via
``_collect_validation_flags(...)`` and then **discarded the return value**::

    if policy.get("grade_approval_auto_validate", True):
        _collect_validation_flags(trimmed, ...)   # <- result thrown away

The dedicated ``validation_flags`` model field had been dropped (migrations
0019-0021), and ``grade_approval_detail`` hardcoded ``validation_flags = []``.
So the ``grade_approval_auto_validate`` admin toggle (default ON) did nothing --
the approver never saw the missing-component / out-of-range warnings it was
supposed to raise before they signed off on a class's grades.

Fix: the flags are stored in the surviving ``summary`` JSONField at request time
and read back in the detail view (the template already renders them). The dead
per-request deadline computation on the same lines (its ``deadline_at`` field
and ``is_overdue`` were deliberately removed) was cleaned up.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.evals.approval import create_grade_approval_request
from apps.evals.models import TeacherAssignment
from apps.people.models import StudentProfile, TeacherProfile
from apps.platform_runtime.helpers import (
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)


class GradeApprovalAutoValidateSurfacesFlagsTests(TestCase):

    def setUp(self):
        self.site_settings = get_platform_site_settings_record(create=True)
        self.site_settings.apply_feature_control_state(
            field_updates={
                "grade_approval_enabled": True,
                "grade_approval_roles": ["DEAN"],
                "grade_post_roles": ["DEAN"],
            },
        )
        invalidate_effective_site_settings_cache()

        self.year = AcademicYear.objects.create(
            name="2025/2026", start_date="2025-09-01",
            end_date="2026-08-31", is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="FIRST", position=1,
            start_date="2025-09-01", end_date="2025-11-30", is_active=True,
        )
        dept = Department.objects.create(name="Science", code="SCI-AV")
        self.specialty = Specialty.objects.create(
            department=dept, name="Physics", code="PHY-AV"
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year, department=dept, name="SS3A", code="SS3A-AV"
        )
        self.subject = Subject.objects.create(name="Physics AV")
        self.subject_assignment = SubjectAssignment.objects.create(
            academic_year=self.year, term=self.term, classroom=self.classroom,
            specialty=self.specialty, subject=self.subject, coefficient=1.0,
        )
        self.teacher_user = User.objects.create_user(
            "av_teacher", "av_teacher@example.com", "pass", role=User.Role.TEACHER
        )
        self.teacher_profile = TeacherProfile.objects.create(user=self.teacher_user)
        TeacherAssignment.objects.create(
            teacher=self.teacher_profile, academic_year=self.year,
            subject_assignment=self.subject_assignment, is_active=True,
        )
        self.student = StudentProfile.objects.create(
            first_name="Jane", last_name="Doe", student_code="AV-STU001",
            academic_year=self.year, classroom=self.classroom,
            specialty=self.specialty, is_active=True,
        )
        self.dean_user = User.objects.create_user(
            "av_dean", "av_dean@example.com", "secret", role=User.Role.DEAN
        )
        self.dean_user.is_staff = True
        self.dean_user.save()

    def _entries(self, *, seq1="18"):
        """All five components present (so no missing-required noise); vary seq1
        to move it in/out of the 0-20 range."""
        return [
            {
                "student_id": self.student.id,
                "student_code": self.student.student_code,
                "student_name": "Doe Jane",
                "scores": {
                    "seq1": Decimal(seq1), "seq2": Decimal("17"),
                    "exam": Decimal("16"), "mock": Decimal("15"),
                    "practical": Decimal("14"),
                },
                "remarks": "",
                "has_scores": True,
            }
        ]

    def _create(self, entries):
        return create_grade_approval_request(
            teacher=self.teacher_profile,
            subject_assignment=self.subject_assignment,
            academic_year=self.year,
            term=self.term,
            entries=entries,
            requested_by=self.teacher_user,
        )

    def test_auto_validate_surfaces_flags_in_summary(self):
        """The bug: flags were computed then thrown away."""
        req = self._create(self._entries(seq1="25"))  # 25 on a 0-20 scale
        flags = (req.summary or {}).get("validation_flags")
        self.assertTrue(
            flags,
            "auto-validate computed flags but stored none -- the "
            "grade_approval_auto_validate toggle surfaced nothing to the approver",
        )
        self.assertIn("score_out_of_range", [f["code"] for f in flags])

    def test_clean_submission_stores_empty_flags(self):
        """The flags must reflect the data, not always fire."""
        req = self._create(self._entries(seq1="18"))
        self.assertEqual((req.summary or {}).get("validation_flags"), [])

    def test_summary_keeps_its_existing_keys(self):
        req = self._create(self._entries(seq1="18"))
        self.assertEqual(req.summary.get("total_students"), 1)
        self.assertEqual(req.summary.get("submitted_rows"), 1)

    def test_detail_view_surfaces_stored_flags(self):
        """End-to-end: the approver actually sees the warning."""
        req = self._create(self._entries(seq1="25"))
        self.client.login(username="av_dean", password="secret")
        resp = self.client.get(
            reverse("evals:grade_approval_detail", args=[req.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            resp.context["validation_flags"],
            "the detail view hardcoded validation_flags=[] so the approver "
            "never saw the flags stored on the request",
        )
        self.assertContains(resp, "Validation flags")

    def test_toggle_off_stores_no_flags(self):
        self.site_settings.apply_feature_control_state(
            field_updates={"grade_approval_auto_validate": False},
        )
        invalidate_effective_site_settings_cache()
        req = self._create(self._entries(seq1="25"))
        self.assertFalse(
            (req.summary or {}).get("validation_flags"),
            "auto-validate was toggled OFF but flags were still computed/stored",
        )
