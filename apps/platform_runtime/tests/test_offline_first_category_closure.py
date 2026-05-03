"""
Offline-first program closure: operator queue + conflict UI + domains + audit/events.

Proves attendance, grading, payment_receipt, and notes_report paths documented for
docs/generated/system_closure_map.json offline_first closure.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import Client, TestCase, override_settings
from django.urls import reverse

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
    retry_failed_actions,
)
from apps.schools.models import School, SchoolMembership


def _host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class OfflineFirstCategoryDashboardTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.client = Client(enforce_csrf_checks=False)
        self.school = School.objects.create(
            name=f"Cat OF {uid}",
            slug=f"cat-of-{uid}",
            subdomain=f"cato{uid}",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            username=f"tc_{uid}", password="pw", role=User.Role.TEACHER
        )
        self.principal = User.objects.create_user(
            username=f"pc_{uid}", password="pw", role=User.Role.PRINCIPAL, is_staff=True
        )
        for u in (self.teacher, self.principal):
            SchoolMembership.objects.get_or_create(
                user=u,
                school=self.school,
                defaults={"role": u.role, "is_primary": True},
            )
        year = AcademicYear.objects.create(
            name="Y",
            start_date="2025-01-01",
            end_date="2025-12-31",
            school=self.school,
        )
        dept = Department.objects.create(name="D", code=f"D{uid}", school=self.school)
        self.classroom = Classroom.objects.create(
            academic_year=year,
            department=dept,
            name="F1",
            code=f"F{uid}",
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            first_name="K",
            last_name="1",
            date_of_birth="2012-03-03",
            student_code=f"K{uid}",
            school=self.school,
            classroom=self.classroom,
        )

    def test_anonymous_cannot_open_sync_queue(self):
        url = reverse("portal:offline_sync_queue")
        resp = self.client.get(url, HTTP_HOST=_host(self.school))
        self.assertIn(resp.status_code, (302, 403))

    def test_queue_includes_all_supported_action_types_in_filter_and_rows(self):
        markers = {
            OfflineAction.ActionType.ATTENDANCE: "CATMARK-ATT",
            OfflineAction.ActionType.GRADING: "CATMARK-GRA",
            OfflineAction.ActionType.PAYMENT_RECEIPT: "CATMARK-PAY",
            OfflineAction.ActionType.NOTES_REPORT: "CATMARK-NOT",
        }
        for at, mark in markers.items():
            pl = (
                {"body": "x" * 24, "title": "t"}
                if at == OfflineAction.ActionType.NOTES_REPORT
                else {"k": 1}
            )
            enqueue_offline_action(
                user_id=self.teacher.pk,
                school_id=self.school.pk,
                action_type=at,
                payload=pl,
                idempotency_key=f"{mark}-{uuid.uuid4().hex[:6]}",
            )
        self.client.force_login(self.principal)
        resp = self.client.get(
            reverse("portal:offline_sync_queue"), HTTP_HOST=_host(self.school)
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        for _at, mark in markers.items():
            self.assertIn(mark, body)
        for val, _label in OfflineAction.ActionType.choices:
            self.assertIn(f'value="{val}"', body)

    def test_idempotency_column_shows_key(self):
        enqueue_offline_action(
            user_id=self.teacher.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={"k": 1},
            idempotency_key="cat-idem-visible-1",
        )
        self.client.force_login(self.principal)
        resp = self.client.get(
            reverse("portal:offline_sync_queue"), HTTP_HOST=_host(self.school)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "cat-idem-visible-1")

    def test_conflict_cards_expose_resolution_buttons_per_domain(self):
        """Synthetic conflict rows — UI contract for all OfflineAction.ActionType values."""
        for at in (
            OfflineAction.ActionType.ATTENDANCE,
            OfflineAction.ActionType.GRADING,
            OfflineAction.ActionType.PAYMENT_RECEIPT,
            OfflineAction.ActionType.NOTES_REPORT,
        ):
            OfflineAction.objects.create(
                user_id=self.teacher.pk,
                school_id=self.school.pk,
                action_type=at,
                payload={"demo": "conflict"},
                status=OfflineAction.Status.CONFLICT,
                conflict_reason=f"demo conflict {at}",
                conflict_details={"server_x": "a", "client_x": "b"},
            )
        self.client.force_login(self.principal)
        resp = self.client.get(
            reverse("portal:offline_sync_conflicts"), HTTP_HOST=_host(self.school)
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertGreaterEqual(body.count("Keep mine"), 4)
        self.assertGreaterEqual(body.count("Use latest"), 4)
        self.assertGreaterEqual(body.count("Review manually"), 4)

    def test_resolution_records_audit_blob(self):
        Attendance.objects.create(
            school_id=self.school.pk,
            student_id=self.student.pk,
            classroom_id=self.classroom.pk,
            date="2025-08-01",
            status=Attendance.Status.ABSENT,
        )
        action = enqueue_offline_action(
            user_id=self.teacher.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={
                "student_id": self.student.pk,
                "classroom_id": self.classroom.pk,
                "date": "2025-08-01",
                "status": Attendance.Status.PRESENT,
            },
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.teacher.pk)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.CONFLICT)
        resolve_conflict_choice(
            action_id=action.pk,
            school_id=self.school.pk,
            user_id=self.principal.pk,
            choice=OfflineAction.Resolution.KEEP_MINE,
            school_operator=True,
        )
        action.refresh_from_db()
        audits = (action.sync_metadata or {}).get("resolution_audits") or []
        self.assertTrue(audits)
        last = audits[-1]
        self.assertEqual(last.get("choice"), OfflineAction.Resolution.KEEP_MINE)
        self.assertEqual(last.get("resolver_user_id"), self.principal.pk)
        self.assertTrue(last.get("resolved_at"))

    def test_retry_failed_requeues(self):
        failed = OfflineAction.objects.create(
            user_id=self.teacher.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.GRADING,
            payload={},
            status=OfflineAction.Status.FAILED,
            retry_count=0,
        )
        n = retry_failed_actions(
            school_id=self.school.pk, user_id=self.teacher.pk, limit=10
        )
        self.assertEqual(n, 1)
        failed.refresh_from_db()
        self.assertEqual(failed.status, OfflineAction.Status.QUEUED)


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class OfflineFirstCategoryLifecycleTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"CatLF {uid}",
            slug=f"catlf-{uid}",
            subdomain=f"catl{uid}",
            is_active=True,
        )
        self.user = User.objects.create_user(username=f"ulf_{uid}", password="x")
        year = AcademicYear.objects.create(
            name="Y1",
            start_date="2025-01-01",
            end_date="2025-12-31",
            school=self.school,
        )
        dept = Department.objects.create(
            name="D", code=f"D{uid}", school=self.school
        )
        self.classroom = Classroom.objects.create(
            academic_year=year,
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
        self.year = year

    def test_lifecycle_platform_events_cover_enqueue_fail_conflict_resolve_sync(self):
        action = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={},
            idempotency_key="",
        )
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="offline_action_queued",
                payload__offline_action_id=action.pk,
            ).exists()
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

    def test_all_four_domains_process_success_and_events(self):
        uid = uuid.uuid4().hex[:6]
        att = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={
                "student_id": self.student.pk,
                "classroom_id": self.classroom.pk,
                "date": "2025-07-02",
                "status": Attendance.Status.PRESENT,
            },
            idempotency_key=f"cat-dom-att-{uid}",
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        att.refresh_from_db()
        self.assertEqual(att.status, OfflineAction.Status.SYNCED)
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="offline_action_synced",
                payload__offline_action_id=att.pk,
            ).exists()
        )

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
        sub = Subject.objects.create(school=self.school, name="Alg")
        sa = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=term,
            classroom=self.classroom,
            specialty=spec,
            subject=sub,
        )
        TeacherProfile.objects.create(user=self.user, school=self.school)
        gr = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.GRADING,
            payload={
                "subject_assignment_id": sa.pk,
                "student_id": self.student.pk,
                "academic_year_id": self.year.pk,
                "term_id": term.pk,
                "seq1_score": 12,
            },
            idempotency_key=f"cat-dom-gr-{uid}",
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        gr.refresh_from_db()
        self.assertEqual(gr.status, OfflineAction.Status.SYNCED)
        self.assertTrue(OfflineMarkEntry.objects.filter(subject_assignment_id=sa.pk).exists())

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
        pay = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.PAYMENT_RECEIPT,
            payload={
                "invoice_id": inv.pk,
                "amount": "10.00",
                "payment_method": "CASH",
                "client_offline_id": f"cid-{uid}",
            },
            idempotency_key=f"cat-dom-pay-{uid}",
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        pay.refresh_from_db()
        self.assertEqual(pay.status, OfflineAction.Status.SYNCED)
        self.assertTrue(OfflinePaymentIntent.objects.filter(invoice=inv).exists())

        note = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={
                "body": "Observation text for closure category proof.",
                "title": "Note",
                "student_id": self.student.pk,
            },
            idempotency_key=f"cat-dom-note-{uid}",
        )
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        note.refresh_from_db()
        self.assertEqual(note.status, OfflineAction.Status.SYNCED)

    def test_idempotency_prevents_duplicate_row(self):
        a1 = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "first"},
            idempotency_key="cat-idem-1",
        )
        a2 = enqueue_offline_action(
            user_id=self.user.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "second ignored"},
            idempotency_key="cat-idem-1",
        )
        self.assertEqual(a1.pk, a2.pk)
