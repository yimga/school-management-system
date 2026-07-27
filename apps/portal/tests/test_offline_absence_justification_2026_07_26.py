"""Offline parent absence-justification lands a real AttendanceJustification.

Before this, the parent justification form queued offline as a generic
``notes_report`` and replayed into an opaque, student-less StudentNote that
staff had to re-key. It is now a structured ``field_capture`` workflow whose
server handler writes the same ``portal.AttendanceJustification`` the online
ModelForm does — RBAC-gated to the caller's own children and idempotent on
reconnect replay. These tests drive the real server dispatch
(``_apply_notes_report`` -> ``try_apply_field_capture_workflow``).
"""

from __future__ import annotations

import json
from datetime import date

from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
)
from apps.accounts.models import User
from apps.people.models import StudentGuardian, StudentProfile
from apps.platform_runtime.offline_queue import _apply_notes_report
from apps.portal.models import AttendanceJustification
from apps.schools.models import School


def _justification_payload(*, student_id, attendance_date="2026-07-20", reason="Fever"):
    body = json.dumps(
        {
            "workflow": "absence_justification",
            "fields": {
                "student": str(student_id),
                "attendance_date": attendance_date,
                "reason": reason,
            },
            "captured_at": "2026-07-20T08:00:00Z",
            "page_path": "/portal/parent/attendance-discipline/",
        }
    )
    return {"body": body, "title": "absence justification", "kind": "note"}


class OfflineAbsenceJustificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="AJ School", slug="aj-school", subdomain="aj-school", is_active=True
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        cls.dept = Department.objects.create(
            school=cls.school, name="General", code="GEN-AJ"
        )
        cls.specialty = Specialty.objects.create(
            school=cls.school, department=cls.dept, name="General", code="GEN-AJ-S"
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=cls.dept,
            name="Form 1A",
            code="F1A-AJ",
        )
        cls.child = StudentProfile.objects.create(
            first_name="Ama",
            last_name="AJ",
            student_code="STU-AJ-1",
            classroom=cls.classroom,
            academic_year=cls.year,
            specialty=cls.specialty,
            school=cls.school,
        )
        cls.parent = User.objects.create_user(
            username="parent_aj", password="pass", role=User.Role.PARENT
        )
        StudentGuardian.objects.create(
            guardian_user=cls.parent,
            student=cls.child,
            relationship=StudentGuardian.Relationship.GUARDIAN,
        )
        # A parent of some OTHER family (must not be able to justify cls.child).
        cls.stranger = User.objects.create_user(
            username="stranger_aj", password="pass", role=User.Role.PARENT
        )

    def test_offline_justification_creates_real_row(self):
        result = _apply_notes_report(
            self.school.id,
            self.parent.id,
            _justification_payload(student_id=self.child.id, reason="Medical appointment"),
        )
        self.assertTrue(result.get("ok"), result)
        self.assertTrue(result.get("created"))
        j = AttendanceJustification.objects.get(pk=result["attendance_justification_id"])
        self.assertEqual(j.guardian_id, self.parent.id)
        self.assertEqual(j.student_id, self.child.id)
        self.assertEqual(j.attendance_date, date(2026, 7, 20))
        self.assertEqual(j.reason, "Medical appointment")

    def test_offline_justification_rbac_denies_non_guardian(self):
        result = _apply_notes_report(
            self.school.id,
            self.stranger.id,
            _justification_payload(student_id=self.child.id),
        )
        self.assertFalse(result.get("ok"))
        self.assertFalse(
            AttendanceJustification.objects.filter(
                guardian_id=self.stranger.id
            ).exists()
        )

    def test_offline_justification_replay_is_idempotent(self):
        payload = _justification_payload(student_id=self.child.id, reason="Travel")
        first = _apply_notes_report(self.school.id, self.parent.id, payload)
        second = _apply_notes_report(self.school.id, self.parent.id, payload)
        self.assertTrue(first.get("ok") and second.get("ok"))
        self.assertTrue(first.get("created"))
        self.assertTrue(second.get("idempotent"))
        self.assertEqual(
            AttendanceJustification.objects.filter(
                guardian_id=self.parent.id,
                student_id=self.child.id,
                attendance_date=date(2026, 7, 20),
            ).count(),
            1,
        )

    def test_offline_justification_rejects_missing_fields(self):
        payload = _justification_payload(student_id=self.child.id, reason="")
        result = _apply_notes_report(self.school.id, self.parent.id, payload)
        self.assertFalse(result.get("ok"))
        self.assertEqual(AttendanceJustification.objects.count(), 0)
