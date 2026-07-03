"""Wave C — record merge e2e (design D6 exit criterion).

Two seeded duplicate students merge with every inbound-FK row re-parented
or quarantined: clean attendance/guardian rows move to the primary, the
deliberately-colliding attendance row (same student+classroom+date unique
boundary on both sides) QUARANTINES on the operation — never deleted —
and the secondary soft-retires (is_active=False + merged_into tombstone).
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import AcademicYear, Attendance, Classroom, Department
from apps.people.merge_service import (
    MergeBlockedError,
    apply_merge,
    approve_merge,
    inbound_fk_fields,
    preview_merge,
)
from apps.people.models import StudentGuardian, StudentProfile
from apps.people.models_merge import MergeStateError, RecordMergeOperation
from apps.schools.models import School

User = get_user_model()


class RecordMergeEngineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Merge High", slug="merge-high", subdomain="merge-high"
        )
        self.other_school = School.objects.create(
            name="Other High", slug="merge-other", subdomain="merge-other"
        )
        year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
        )
        department = Department.objects.create(
            school=self.school, name="Science", code="SCI-MG"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=year,
            department=department,
            name="Form 2B",
            code="F2B-MG",
        )
        self.primary = StudentProfile.objects.create(
            school=self.school,
            first_name="Dupe",
            last_name="Licate",
            student_code="MG-PRIMARY",
        )
        self.secondary = StudentProfile.objects.create(
            school=self.school,
            first_name="Dupe",
            last_name="Licate",
            student_code="MG-SECOND",
        )
        guardian_user = User.objects.create_user(
            username="mg_guardian", password="pass123"
        )
        # Clean rows on the secondary: one guardian link + one attendance day
        # the primary does NOT have.
        StudentGuardian.objects.create(
            guardian_user=guardian_user, student=self.secondary, phone="+237600000009"
        )
        Attendance.objects.create(
            school=self.school,
            student=self.secondary,
            classroom=self.classroom,
            date=date(2025, 10, 1),
        )
        # Collision row: BOTH sides hold attendance for the same
        # (classroom, date) — re-pointing the secondary's row violates
        # unique (student, classroom, date) and must quarantine.
        Attendance.objects.create(
            school=self.school,
            student=self.primary,
            classroom=self.classroom,
            date=date(2025, 10, 2),
        )
        Attendance.objects.create(
            school=self.school,
            student=self.secondary,
            classroom=self.classroom,
            date=date(2025, 10, 2),
        )
        self.operator = User.objects.create_user(
            username="mg_operator", password="pass123", is_staff=True
        )
        self.op = RecordMergeOperation.objects.create(
            school=self.school,
            kind=RecordMergeOperation.Kind.STUDENT,
            primary_pk=str(self.primary.pk),
            secondary_pk=str(self.secondary.pk),
            created_by=self.operator,
        )

    def _run_full(self):
        preview_merge(self.op)
        approve_merge(self.op, self.operator)
        return apply_merge(self.op, actor=self.operator)

    def test_walker_sees_the_known_relations(self):
        labels = {
            f"{model._meta.label_lower}.{field.name}"
            for model, field in inbound_fk_fields(StudentProfile)
        }
        self.assertIn("academics.attendance.student", labels)
        self.assertIn("people.studentguardian.student", labels)
        # The tombstone self-FK is walkable too (chain compression).
        self.assertIn("people.studentprofile.merged_into", labels)

    def test_preview_counts_the_footprint(self):
        preview = preview_merge(self.op)
        self.op.refresh_from_db()
        self.assertEqual(self.op.status, RecordMergeOperation.Status.PREVIEWED)
        self.assertEqual(
            preview["repoint"]["academics.attendance.student"], 2
        )
        self.assertEqual(
            preview["repoint"]["people.studentguardian.student"], 1
        )

    def test_apply_repoints_quarantines_and_tombstones(self):
        summary = self._run_full()
        self.op.refresh_from_db()
        self.primary.refresh_from_db()
        self.secondary.refresh_from_db()

        self.assertEqual(self.op.status, RecordMergeOperation.Status.APPLIED)

        # Clean rows moved: guardian link + the 10-01 attendance day.
        self.assertTrue(
            StudentGuardian.objects.filter(student=self.primary).exists()
        )
        self.assertTrue(
            Attendance.objects.filter(
                student=self.primary, date=date(2025, 10, 1)
            ).exists()
        )

        # The colliding 10-02 row QUARANTINED: still on the retired
        # secondary, listed on the operation, never deleted.
        self.assertTrue(
            Attendance.objects.filter(
                student=self.secondary, date=date(2025, 10, 2)
            ).exists()
        )
        self.assertEqual(
            Attendance.objects.filter(
                classroom=self.classroom, date=date(2025, 10, 2)
            ).count(),
            2,
        )
        collision_models = {c["model"] for c in self.op.collisions}
        self.assertIn("academics.attendance", collision_models)
        self.assertGreaterEqual(summary["collisions"], 1)

        # Tombstone: soft-retired, pointing at the survivor.
        self.assertFalse(self.secondary.is_active)
        self.assertEqual(self.secondary.merged_into_id, self.primary.pk)

        # Lineage stamped on the survivor.
        from apps.metadata.models_derived_lineage import DerivedValueLineage

        self.assertTrue(
            DerivedValueLineage.objects.filter(
                computation="people.merge",
                output_pk=str(self.primary.pk),
            ).exists()
        )

    def test_apply_requires_approval(self):
        preview_merge(self.op)
        with self.assertRaises(MergeBlockedError):
            apply_merge(self.op, actor=self.operator)

    def test_cross_school_refused(self):
        stranger = StudentProfile.objects.create(
            school=self.other_school,
            first_name="Not",
            last_name="Here",
            student_code="MG-STRANGER",
        )
        op = RecordMergeOperation.objects.create(
            school=self.school,
            kind=RecordMergeOperation.Kind.STUDENT,
            primary_pk=str(self.primary.pk),
            secondary_pk=str(stranger.pk),
        )
        with self.assertRaises(MergeBlockedError):
            preview_merge(op)

    def test_already_merged_secondary_refused(self):
        self._run_full()
        op2 = RecordMergeOperation.objects.create(
            school=self.school,
            kind=RecordMergeOperation.Kind.STUDENT,
            primary_pk=str(self.primary.pk),
            secondary_pk=str(self.secondary.pk),
        )
        with self.assertRaises(MergeBlockedError):
            preview_merge(op2)

    def test_illegal_transition_raises(self):
        with self.assertRaises(MergeStateError):
            self.op.advance(RecordMergeOperation.Status.APPLIED)

    def test_merge_records_wrapper_runs_end_to_end(self):
        from apps.people.people_management import RecordManagementService

        result = RecordManagementService.merge_records(
            self.primary, self.secondary, actor=self.operator
        )
        self.secondary.refresh_from_db()
        self.assertFalse(self.secondary.is_active)
        self.assertEqual(result["merged_into"], self.primary.pk)
        self.assertGreaterEqual(result["repointed"], 2)
        self.assertGreaterEqual(result["quarantined"], 1)


class MergeConsoleTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Console Merge", slug="console-merge", subdomain="console-merge"
        )
        self.primary = StudentProfile.objects.create(
            school=self.school, first_name="A", last_name="B", student_code="CM-P"
        )
        self.secondary = StudentProfile.objects.create(
            school=self.school, first_name="A", last_name="B", student_code="CM-S"
        )
        self.staff = User.objects.create_user(
            username="cm_staff", password="pass123", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.staff)

    def test_non_staff_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("portal:merge_ops_index"))
        self.assertEqual(response.status_code, 302)

    def test_create_approve_apply_flow(self):
        response = self.client.post(
            reverse("portal:merge_op_create"),
            {
                "kind": "student",
                "primary_pk": str(self.primary.pk),
                "secondary_pk": str(self.secondary.pk),
                "format": "json",
            },
        )
        self.assertEqual(response.status_code, 201)
        op_id = response.json()["operation"]["id"]
        self.assertEqual(response.json()["operation"]["status"], "previewed")

        response = self.client.post(
            reverse("portal:merge_op_approve"),
            {"operation_id": op_id, "format": "json"},
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("portal:merge_op_apply"),
            {"operation_id": op_id, "format": "json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["operation"]["status"], "applied")
        self.secondary.refresh_from_db()
        self.assertFalse(self.secondary.is_active)

    def test_apply_without_approval_409(self):
        response = self.client.post(
            reverse("portal:merge_op_create"),
            {
                "kind": "student",
                "primary_pk": str(self.primary.pk),
                "secondary_pk": str(self.secondary.pk),
                "format": "json",
            },
        )
        op_id = response.json()["operation"]["id"]
        response = self.client.post(
            reverse("portal:merge_op_apply"),
            {"operation_id": op_id, "format": "json"},
        )
        self.assertEqual(response.status_code, 409)

    def test_same_pk_rejected(self):
        response = self.client.post(
            reverse("portal:merge_op_create"),
            {
                "kind": "student",
                "primary_pk": str(self.primary.pk),
                "secondary_pk": str(self.primary.pk),
                "format": "json",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_html_index_renders(self):
        response = self.client.get(reverse("portal:merge_ops_index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Record merges")
