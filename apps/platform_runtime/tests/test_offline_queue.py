"""Tests for apps.platform_runtime.offline_queue."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Attendance, Classroom, Department
from apps.finance.models import ComplianceProfile, Invoice, OfflinePaymentIntent
from apps.people.models import StudentProfile
from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import (
    enqueue_offline_action,
    mark_synced,
    merge_conflict_records,
    next_retry_delay_seconds,
    process_offline_queue,
    resolve_conflict_choice,
    retry_failed_actions,
)
from apps.schools.models import School


class OfflineQueueHelpersTests(TestCase):
    def test_retry_backoff_caps(self):
        self.assertEqual(next_retry_delay_seconds(0), 5)
        self.assertEqual(next_retry_delay_seconds(99), 1800)

    def test_merge_last_write_wins(self):
        rows = [
            {"entity": "Attendance", "id": "9", "revision": 1, "v": "a"},
            {"entity": "Attendance", "id": "9", "revision": 3, "v": "b"},
        ]
        merged = merge_conflict_records(rows, strategy="last_write_wins")
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["v"], "b")


class OfflineActionQueueTests(TestCase):
    """Durable OfflineAction: enqueue, process, conflict, tenant scope, payment receipt."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"OffQ {uid}",
            slug=f"offq-{uid}",
            subdomain=f"offq{uid}",
            is_active=True,
        )
        self.other_school = School.objects.create(
            name=f"Other {uid}",
            slug=f"other-{uid}",
            subdomain=f"oth{uid}",
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

    def test_enqueue_process_attendance_mark_synced(self):
        action = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={
                "student_id": self.student.pk,
                "classroom_id": self.classroom.pk,
                "date": "2025-06-01",
                "status": Attendance.Status.PRESENT,
            },
        )
        self.assertEqual(action.status, OfflineAction.Status.QUEUED)
        out = process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        self.assertEqual(out["synced"], 1)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.SYNCED)
        att = Attendance.objects.get(
            student_id=self.student.pk,
            classroom_id=self.classroom.pk,
            date="2025-06-01",
        )
        self.assertEqual(att.status, Attendance.Status.PRESENT)

        mark_synced(action.pk, school_id=self.school.pk, metadata={"x": 1})
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.SYNCED)
        self.assertEqual(action.sync_metadata.get("x"), 1)

    def test_conflict_then_keep_mine(self):
        Attendance.objects.create(
            school_id=self.school.pk,
            student_id=self.student.pk,
            classroom_id=self.classroom.pk,
            date="2025-06-02",
            status=Attendance.Status.ABSENT,
        )
        action = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={
                "student_id": self.student.pk,
                "classroom_id": self.classroom.pk,
                "date": "2025-06-02",
                "status": Attendance.Status.PRESENT,
            },
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.CONFLICT)

        r = resolve_conflict_choice(
            action_id=action.pk,
            school_id=self.school.pk,
            user_id=self.user.pk,
            choice=OfflineAction.Resolution.KEEP_MINE,
        )
        self.assertTrue(r.get("ok"))
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.SYNCED)
        att = Attendance.objects.get(
            student_id=self.student.pk,
            classroom_id=self.classroom.pk,
            date="2025-06-02",
        )
        self.assertEqual(att.status, Attendance.Status.PRESENT)

    def test_retry_failed(self):
        action = OfflineAction.objects.create(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={},
            status=OfflineAction.Status.FAILED,
            retry_count=0,
        )
        n = retry_failed_actions(school_id=self.school.pk, user_id=self.user.pk)
        self.assertEqual(n, 1)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.QUEUED)
        self.assertEqual(action.retry_count, 1)

    def test_tenant_isolation(self):
        action = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={
                "student_id": self.student.pk,
                "classroom_id": self.classroom.pk,
                "date": "2025-07-01",
                "status": Attendance.Status.PRESENT,
            },
        )
        self.assertFalse(
            OfflineAction.objects.filter(
                school_id=self.other_school.pk, pk=action.pk
            ).exists()
        )

    def test_offline_payment_receipt_queues_intent(self):
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
        enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.PAYMENT_RECEIPT,
            payload={
                "invoice_id": inv.pk,
                "amount": "10.00",
                "payment_method": "CASH",
                "client_offline_id": "rcpt-1",
            },
            idempotency_key="pay-rcpt-1",
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        intent = OfflinePaymentIntent.objects.filter(invoice=inv).first()
        self.assertIsNotNone(intent)
        self.assertEqual(intent.amount, Decimal("10.00"))

    def test_enqueue_idempotent(self):
        a1 = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={"k": 1},
            idempotency_key="idem-1",
        )
        a2 = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={"k": 2},
            idempotency_key="idem-1",
        )
        self.assertEqual(a1.pk, a2.pk)
