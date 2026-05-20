"""Stage 6 academic operations repo-scope contracts (orchestrator wave)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.automation.domain_event_bridge import resolve_trigger_key
from apps.automation.workflow_trigger_catalog import FULL_TRIGGER_CATALOG_KEYS
from apps.communication import tasks as comm_tasks
from emis.services import EMISExportService


class AcademicOperationsContractSimpleTests(SimpleTestCase):
    def test_offline_action_conflict_in_full_trigger_catalog(self):
        self.assertIn("offline_action_conflict", FULL_TRIGGER_CATALOG_KEYS)

    def test_domain_event_bridge_resolves_offline_conflict(self):
        self.assertEqual(
            resolve_trigger_key("offline_action_conflict"),
            "offline_action_conflict",
        )

    def test_communication_outbound_queue_task_registered(self):
        self.assertTrue(
            hasattr(comm_tasks, "process_outbound_message_queue"),
            "async notification path via Celery outbound queue",
        )


class EMISTenantIsolationContractTests(TestCase):
    """EMIS exports stay schema-safe; relational evals drive performance rows."""

    def test_emis_performance_export_uses_relational_evaluations(self):
        from apps.academics.models import (
            AcademicYear,
            Classroom,
            Department,
            Specialty,
            Subject,
            SubjectAssignment,
            Term,
        )
        from apps.evals.models import Evaluation, TeacherAssignment
        from apps.people.models import StudentProfile, TeacherProfile

        year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        term = Term.objects.create(
            academic_year=year,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 20),
            position=1,
            is_active=True,
        )
        dept = Department.objects.create(name="General", code="GEN")
        spec = Specialty.objects.create(department=dept, name="General", code="GEN")
        classroom = Classroom.objects.create(
            academic_year=year,
            department=dept,
            name="Form 1",
            code="F1",
        )
        subject = Subject.objects.create(name="Math", category=Subject.Category.GENERAL)
        sa = SubjectAssignment.objects.create(
            academic_year=year,
            term=term,
            classroom=classroom,
            specialty=spec,
            subject=subject,
            coefficient=1,
        )
        teacher_user = User.objects.create_user(
            username="t_stage6",
            password="x",
            role=User.Role.TEACHER,
        )
        teacher = TeacherProfile.objects.create(
            user=teacher_user,
            department=dept,
            position_title="Teacher",
            phone="670000001",
            staff_id="T-S6",
        )
        TeacherAssignment.objects.create(
            teacher=teacher,
            academic_year=year,
            subject_assignment=sa,
            is_active=True,
        )
        student = StudentProfile.objects.create(
            first_name="A",
            last_name="Student",
            student_code="S6-001",
            date_of_birth=date(2012, 1, 1),
            academic_year=year,
            classroom=classroom,
            specialty=spec,
            is_active=True,
        )
        Evaluation.objects.create(
            academic_year=year,
            term=term,
            subject_assignment=sa,
            student=student,
            teacher=teacher,
            seq1_score=Decimal("10.00"),
            seq2_score=Decimal("11.00"),
            exam_score=Decimal("12.00"),
        )

        perf = EMISExportService("CMR").export_performance(year, term)
        self.assertEqual(perf["count"], 1)
        row = perf["data"][0]
        self.assertIn("average_performance", row)
        self.assertIsNotNone(row.get("average_performance"))


class Student360AccessContractTests(SimpleTestCase):
    def test_student360_views_require_login(self):
        from apps.student360 import views as s360_views

        for name in ("student_360_page", "student_360_export"):
            fn = getattr(s360_views, name, None)
            self.assertIsNotNone(fn, name)
            self.assertTrue(
                hasattr(fn, "__wrapped__") or "login_required" in str(fn),
                f"{name} must be login-gated",
            )


class ReportsPublishContractTests(SimpleTestCase):
    def test_publish_term_route_resolves(self):
        self.assertTrue(reverse("reports:publish_term_results"))
