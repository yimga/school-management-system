"""Metric 25: seven-day offline queue accumulation → single reconnect replay."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Attendance, Classroom, Department
from apps.people.models import StudentProfile
from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import enqueue_offline_action, process_offline_queue
from apps.schools.models import School


class OfflineMultidayReplaySimulationTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Multiday {uid}",
            slug=f"md-{uid}",
            subdomain=f"md{uid}",
            is_active=True,
        )
        self.user = User.objects.create_user(username=f"md_{uid}", password="x")
        self.year = AcademicYear.objects.create(
            name="Y1",
            start_date="2025-01-01",
            end_date="2025-12-31",
            school=self.school,
        )
        dept = Department.objects.create(
            name="D",
            code=f"D{uid}",
            school=self.school,
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=dept,
            name="C1",
            code=f"C{uid}",
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            first_name="S",
            last_name="T",
            date_of_birth="2012-01-01",
            student_code=f"ST{uid}",
            school=self.school,
            classroom=self.classroom,
        )

    def test_seven_day_offline_attendance_replay_converges_idempotently(self):
        """Simulate 7 calendar days of queued writes, then one reconnect batch."""
        base = timezone.now() - timedelta(days=7)
        action_ids: list[int] = []
        for day_offset in range(7):
            work_date = (base + timedelta(days=day_offset)).date().isoformat()
            action = enqueue_offline_action(
                user_id=self.user.pk,
                school_id=self.school.pk,
                action_type=OfflineAction.ActionType.ATTENDANCE,
                payload={
                    "student_id": self.student.pk,
                    "classroom_id": self.classroom.pk,
                    "date": work_date,
                    "status": Attendance.Status.PRESENT,
                },
                idempotency_key=f"md-att-{day_offset}-{self.school.pk}",
            )
            OfflineAction.objects.filter(pk=action.pk).update(
                created_at=base + timedelta(days=day_offset, hours=8),
            )
            action_ids.append(action.pk)

        first = process_offline_queue(
            school_id=self.school.pk,
            user_id=self.user.pk,
            limit=50,
        )
        self.assertGreaterEqual(first.get("synced", 0), 7)
        self.assertEqual(
            OfflineAction.objects.filter(
                pk__in=action_ids,
                status=OfflineAction.Status.SYNCED,
            ).count(),
            7,
        )
        self.assertEqual(
            Attendance.objects.filter(
                school=self.school,
                student=self.student,
                status=Attendance.Status.PRESENT,
            ).count(),
            7,
        )

        second = process_offline_queue(
            school_id=self.school.pk,
            user_id=self.user.pk,
            limit=50,
        )
        self.assertEqual(second.get("synced", 0), 0)

        dup = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={
                "student_id": self.student.pk,
                "classroom_id": self.classroom.pk,
                "date": base.date().isoformat(),
                "status": Attendance.Status.ABSENT,
            },
            idempotency_key="md-att-0-" + str(self.school.pk),
        )
        self.assertEqual(dup.pk, action_ids[0])
        self.assertEqual(dup.status, OfflineAction.Status.SYNCED)

    def test_seven_day_offline_includes_grading_on_reconnect(self):
        from apps.academics.models import Specialty, Subject, SubjectAssignment, Term
        from apps.people.models import TeacherProfile

        TeacherProfile.objects.create(user=self.user, school=self.school)
        term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="T1",
            position=1,
            start_date="2025-01-01",
            end_date="2025-06-30",
            is_active=True,
        )
        spec = Specialty.objects.create(
            school=self.school,
            department=self.classroom.department,
            name="General",
            code=f"G{uuid.uuid4().hex[:8]}",
        )
        self.student.specialty = spec
        self.student.save(update_fields=["specialty"])
        sub = Subject.objects.create(school=self.school, name="Algebra")
        sa = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=term,
            classroom=self.classroom,
            specialty=spec,
            subject=sub,
        )
        action = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.GRADING,
            payload={
                "subject_assignment_id": sa.pk,
                "student_id": self.student.pk,
                "academic_year_id": self.year.pk,
                "term_id": term.pk,
                "seq1_score": 14,
            },
            idempotency_key=f"md-grade-{self.school.pk}",
        )
        OfflineAction.objects.filter(pk=action.pk).update(
            created_at=timezone.now() - timedelta(days=1),
        )
        result = process_offline_queue(
            school_id=self.school.pk,
            user_id=self.user.pk,
            limit=10,
        )
        self.assertGreaterEqual(result.get("synced", 0), 1)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.SYNCED)
