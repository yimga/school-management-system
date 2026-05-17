"""Offline-first closure slice: lifecycle platform events + critical apply paths."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.evals.models import OfflineMarkEntry
from apps.finance.models import ComplianceProfile, Invoice, OfflinePaymentIntent
from apps.people.models import StudentProfile, TeacherProfile
from apps.platform_runtime.models import OfflineAction, PlatformEventLog
from apps.platform_runtime.offline_queue import (
    enqueue_offline_action,
    process_offline_queue,
    resolve_conflict_choice,
)
from apps.schools.models import School


class OfflineFirstClosureSliceTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"OFC {uid}",
            slug=f"ofc-{uid}",
            subdomain=f"ofc{uid}",
            is_active=True,
        )
        self.user = User.objects.create_user(username=f"t_{uid}", password="x")
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

    def test_platform_events_enqueue_conflict_resolve_and_sync(self):
        Attendance.objects.create(
            school_id=self.school.pk,
            student_id=self.student.pk,
            classroom_id=self.classroom.pk,
            date="2025-06-12",
            status=Attendance.Status.ABSENT,
        )
        action = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={
                "student_id": self.student.pk,
                "classroom_id": self.classroom.pk,
                "date": "2025-06-12",
                "status": Attendance.Status.PRESENT,
            },
        )
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="offline_action_queued",
                payload__offline_action_id=action.pk,
            ).exists()
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.CONFLICT)
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="offline_action_conflict",
                payload__offline_action_id=action.pk,
            ).exists()
        )
        r = resolve_conflict_choice(
            action_id=action.pk,
            school_id=self.school.pk,
            user_id=self.user.pk,
            choice=OfflineAction.Resolution.KEEP_MINE,
        )
        self.assertTrue(r.get("ok"))
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.SYNCED)
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="offline_action_resolved",
                payload__offline_action_id=action.pk,
            ).exists()
        )
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="offline_action_synced",
                payload__offline_action_id=action.pk,
            ).exists()
        )

    def test_platform_event_failed_on_domain_apply_error(self):
        action = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={},
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.FAILED)
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="offline_action_failed",
                payload__offline_action_id=action.pk,
            ).exists()
        )

    def test_critical_offline_domains_sync_success(self):
        """Attendance, grading, payment receipt capture, notes/report capture."""
        uid = uuid.uuid4().hex[:6]
        action_att = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={
                "student_id": self.student.pk,
                "classroom_id": self.classroom.pk,
                "date": "2025-07-02",
                "status": Attendance.Status.PRESENT,
            },
            idempotency_key=f"slice-att-{uid}",
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        action_att.refresh_from_db()
        self.assertEqual(action_att.status, OfflineAction.Status.SYNCED)

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
        TeacherProfile.objects.create(user=self.user, school=self.school)
        action_grade = enqueue_offline_action(
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
            idempotency_key=f"slice-gr-{uid}",
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        action_grade.refresh_from_db()
        self.assertEqual(action_grade.status, OfflineAction.Status.SYNCED)
        self.assertTrue(
            OfflineMarkEntry.objects.filter(
                student_id=self.student.pk,
                subject_assignment_id=sa.pk,
            ).exists()
        )

        profile = ComplianceProfile.objects.create(
            name=f"P{uuid.uuid4().hex[:6]}",
            country_code="CM",
        )
        inv = Invoice.objects.create(
            profile=profile,
            academic_year=self.year,
            school=self.school,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal("10.00"),
            balance_amount=Decimal("10.00"),
        )
        action_pay = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.PAYMENT_RECEIPT,
            payload={
                "invoice_id": inv.pk,
                "amount": "10.00",
                "payment_method": "CASH",
                "client_offline_id": f"rcpt-{uid}",
            },
            idempotency_key=f"slice-pay-{uid}",
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        action_pay.refresh_from_db()
        self.assertEqual(action_pay.status, OfflineAction.Status.SYNCED)
        self.assertTrue(
            OfflinePaymentIntent.objects.filter(invoice=inv).exists()
        )

        action_note = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={
                "body": "Student showed improvement during lab.",
                "title": "Weekly note",
                "kind": "quick_capture",
                "student_id": self.student.pk,
            },
            idempotency_key=f"slice-note-{uid}",
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        action_note.refresh_from_db()
        self.assertEqual(action_note.status, OfflineAction.Status.SYNCED)
        meta = action_note.sync_metadata or {}
        self.assertTrue(meta.get("notes_report_capture"))
        self.assertIsNotNone(meta.get("student_note_id"))
        from apps.people.models import StudentNote

        note = StudentNote.objects.get(pk=meta["student_note_id"])
        self.assertEqual(note.body, "Student showed improvement during lab.")
        self.assertEqual(note.student_id, self.student.pk)
        self.assertEqual(note.school_id, self.school.pk)

    def test_enqueue_idempotency_single_row(self):
        a1 = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={"k": 1},
            idempotency_key="idem-slice-1",
        )
        a2 = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={"k": 9},
            idempotency_key="idem-slice-1",
        )
        self.assertEqual(a1.pk, a2.pk)
