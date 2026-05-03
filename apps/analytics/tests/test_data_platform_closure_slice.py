"""
Section 11.4 data_platform closure slice: governed query builder surface + tenant isolation +
saved reports + CSV export audit + closure insights (attendance gap + overdue invoices).
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from django.http import Http404

from apps.accounts.models import Permission
from apps.academics.models import Attendance, Classroom, Department, Specialty
from apps.academics.models import AcademicYear
from apps.analytics.governed_query.executor import GovernedQueryError, execute_governed_query
from apps.analytics.insight_registry import (
    SURFACE_REVENUE,
    build_insights_for_school,
    filter_insights_by_surface,
)
from apps.analytics.models import GovernedSavedReport
from apps.analytics.views_governed import (
    governed_query_export_csv,
    governed_query_preview,
    governed_report_builder,
    governed_saved_report_detail,
    governed_saved_report_save,
    governed_saved_report_run,
)
from apps.compliance.models_audit import AuditLog
from apps.finance.models import ComplianceProfile, Invoice
from apps.people.models import StudentProfile
from apps.schools.models import School

User = get_user_model()


class DataPlatformClosureSliceTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Data Slice A",
            slug="data-slice-a",
            subdomain="data-slice-a",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name="Data Slice B",
            slug="data-slice-b",
            subdomain="data-slice-b",
            is_active=True,
        )
        cls.year_a = AcademicYear.objects.create(
            school=cls.school_a,
            name="AY-A",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        cls.year_b = AcademicYear.objects.create(
            school=cls.school_b,
            name="AY-B",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        cls.dept_a = Department.objects.create(
            school=cls.school_a, name="Dept A", code=f"DA-{uuid.uuid4().hex[:6]}"
        )
        cls.dept_b = Department.objects.create(
            school=cls.school_b, name="Dept B", code=f"DB-{uuid.uuid4().hex[:6]}"
        )
        cls.spec_a = Specialty.objects.create(
            department=cls.dept_a, name="Spec A", code=f"SA-{uuid.uuid4().hex[:4]}"
        )
        cls.spec_b = Specialty.objects.create(
            department=cls.dept_b, name="Spec B", code=f"SB-{uuid.uuid4().hex[:4]}"
        )
        cls.room_a = Classroom.objects.create(
            school=cls.school_a,
            academic_year=cls.year_a,
            department=cls.dept_a,
            name="Class A",
            code=f"CA-{uuid.uuid4().hex[:6]}",
        )
        cls.room_b = Classroom.objects.create(
            school=cls.school_b,
            academic_year=cls.year_b,
            department=cls.dept_b,
            name="Class B",
            code=f"CB-{uuid.uuid4().hex[:6]}",
        )
        cls.student_a = StudentProfile.objects.create(
            school=cls.school_a,
            first_name="Sa",
            last_name="Student",
            student_code=f"S-{uuid.uuid4().hex[:6]}",
            admission_number="ADM-A",
            academic_year=cls.year_a,
            classroom=cls.room_a,
            specialty=cls.spec_a,
            date_of_birth=date(2010, 1, 15),
            is_active=True,
        )
        cls.student_b = StudentProfile.objects.create(
            school=cls.school_b,
            first_name="Sb",
            last_name="Student",
            student_code=f"T-{uuid.uuid4().hex[:6]}",
            admission_number="ADM-B",
            academic_year=cls.year_b,
            classroom=cls.room_b,
            specialty=cls.spec_b,
            date_of_birth=date(2010, 2, 15),
            is_active=True,
        )
        cls.att_a = Attendance.objects.create(
            school=cls.school_a,
            student=cls.student_a,
            classroom=cls.room_a,
            date=date(2025, 11, 10),
            status=Attendance.Status.PRESENT,
        )
        cls.att_b = Attendance.objects.create(
            school=cls.school_b,
            student=cls.student_b,
            classroom=cls.room_b,
            date=date(2025, 11, 10),
            status=Attendance.Status.ABSENT,
        )
        cls.profile = ComplianceProfile.objects.create(
            name="Closure profile",
            country_code="CM",
        )
        cls.inv_a = Invoice.objects.create(
            school=cls.school_a,
            profile=cls.profile,
            academic_year=cls.year_a,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=cls.student_a,
            total_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            due_date=timezone.localdate() - timedelta(days=5),
        )
        cls.inv_b = Invoice.objects.create(
            school=cls.school_b,
            profile=cls.profile,
            academic_year=cls.year_b,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=cls.student_b,
            total_amount=Decimal("60.00"),
            balance_amount=Decimal("60.00"),
            due_date=timezone.localdate() - timedelta(days=3),
        )

        cls.perm_reports, _ = Permission.objects.get_or_create(
            code="reports.manage",
            defaults={"name": "Reports manage"},
        )

    def _staff_reports(self):
        u = User.objects.create_user(
            username="dp_" + uuid.uuid4().hex[:8],
            password="pw",
            is_staff=True,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_reports)
        return u

    def _user_no_reports(self):
        return User.objects.create_user(
            username="nr_" + uuid.uuid4().hex[:8],
            password="pw",
            role=User.Role.EMPLOYER,
        )

    def test_attendance_preview_same_tenant_only(self):
        user = self._staff_reports()
        rows, _ = execute_governed_query(
            user=user,
            school_id=str(self.school_a.pk),
            dataset_id="attendance",
            fields=["id", "student_id"],
            filters={"date": date(2025, 11, 10)},
            limit=50,
        )
        ids = {r["id"] for r in rows}
        self.assertIn(self.att_a.id, ids)
        self.assertNotIn(self.att_b.id, ids)

    def test_invoice_preview_same_tenant_only(self):
        user = self._staff_reports()
        rows, _ = execute_governed_query(
            user=user,
            school_id=str(self.school_a.pk),
            dataset_id="invoices",
            fields=["id", "balance_amount"],
            filters={"balance_amount__gt": 0},
            limit=50,
        )
        ids = {r["id"] for r in rows}
        self.assertIn(self.inv_a.id, ids)
        self.assertNotIn(self.inv_b.id, ids)

    def test_disallowed_field_rejected_attendance(self):
        user = self._staff_reports()
        with self.assertRaises(GovernedQueryError):
            execute_governed_query(
                user=user,
                school_id=str(self.school_a.pk),
                dataset_id="attendance",
                fields=["remarks", "__invalid_field__"],
                limit=5,
            )

    def test_disallowed_filter_rejected(self):
        user = self._staff_reports()
        with self.assertRaises(GovernedQueryError):
            execute_governed_query(
                user=user,
                school_id=str(self.school_a.pk),
                dataset_id="attendance",
                fields=["id"],
                filters={"student__email": "x"},
                limit=5,
            )

    def test_preview_payload_with_sql_noise_does_not_leak_sql(self):
        factory = RequestFactory()
        user = self._staff_reports()
        body = {
            "dataset_id": "students",
            "fields": ["student_code"],
            "limit": 10,
            "sql": "SELECT * FROM students",
            "raw_sql": "DROP TABLE students",
        }
        request = factory.post(
            reverse("analytics:governed_query_preview"),
            data=json.dumps(body),
            content_type="application/json",
        )
        request.user = user
        request.school = self.school_a
        response = governed_query_preview(request)
        payload = json.loads(response.content.decode("utf-8"))
        blob = json.dumps(payload).lower()
        self.assertNotIn("drop table", blob)
        self.assertIn("rows", payload)

    def test_saved_report_create_execute_csv_audit(self):
        user = self._staff_reports()
        factory = RequestFactory()

        before_audit = AuditLog.objects.count()

        save_req = factory.post(
            reverse("analytics:governed_saved_report_save"),
            data=json.dumps(
                {
                    "name": "Slice attendance snapshot",
                    "definition": {
                        "dataset_id": "attendance",
                        "fields": ["id", "status"],
                        "filters": {"date": str(date(2025, 11, 10))},
                        "limit": 50,
                    },
                }
            ),
            content_type="application/json",
        )
        save_req.user = user
        save_req.school = self.school_a
        save_resp = governed_saved_report_save(save_req)
        self.assertEqual(save_resp.status_code, 200)
        save_payload = json.loads(save_resp.content.decode("utf-8"))
        rid = save_payload["id"]

        self.assertTrue(
            AuditLog.objects.filter(
                model_name="GovernedSavedReport",
                object_id=str(rid),
                reason="governed_saved_report_create",
            ).exists()
        )

        run_req = factory.post(
            reverse("analytics:governed_saved_report_run", kwargs={"report_id": rid}),
            data=b"{}",
            content_type="application/json",
        )
        run_req.user = user
        run_req.school = self.school_a
        run_resp = governed_saved_report_run(run_req, rid)
        self.assertEqual(run_resp.status_code, 200)

        csv_req = factory.post(
            reverse("analytics:governed_query_export_csv"),
            data=json.dumps(
                {
                    "dataset_id": "attendance",
                    "fields": ["id"],
                    "filters": {"date": str(date(2025, 11, 10))},
                    "limit": 20,
                }
            ),
            content_type="application/json",
        )
        csv_req.user = user
        csv_req.school = self.school_a
        csv_resp = governed_query_export_csv(csv_req)
        self.assertEqual(csv_resp.status_code, 200)
        self.assertGreater(AuditLog.objects.count(), before_audit)
        self.assertTrue(
            AuditLog.objects.filter(
                model_name="GovernedQueryCsvExport",
                reason="governed_query_export_csv",
            ).exists()
        )

    def test_closure_insights_have_primary_action_urls(self):
        insights = build_insights_for_school(
            str(self.school_a.pk), user=self._staff_reports()
        )
        att = next(
            (i for i in insights if i["id"] == "closure_attendance_gap_missing_roll"),
            None,
        )
        self.assertIsNotNone(att)
        self.assertEqual(att.get("dataset_source"), "attendance")
        self.assertIn("/portal/teacher/attendance/", att["primary_action"]["primary_action_url"])

        pay = next(
            (
                i
                for i in insights
                if i["id"] == "closure_payment_risk_overdue_balance"
            ),
            None,
        )
        self.assertIsNotNone(pay)
        self.assertEqual(pay.get("dataset_source"), "invoices")
        self.assertIn("/finance/invoices/", pay["primary_action"]["primary_action_url"])

        rev = filter_insights_by_surface(insights, SURFACE_REVENUE)
        self.assertTrue(any(i["id"] == "closure_payment_risk_overdue_balance" for i in rev))

    def test_preview_forbidden_without_reports_permission(self):
        factory = RequestFactory()
        user = self._user_no_reports()
        body = {"dataset_id": "students", "fields": ["student_code"], "limit": 5}
        request = factory.post(
            reverse("analytics:governed_query_preview"),
            data=json.dumps(body),
            content_type="application/json",
        )
        request.user = user
        request.school = self.school_a
        response = governed_query_preview(request)
        self.assertEqual(response.status_code, 403)

    def test_saved_report_detail_requires_same_tenant(self):
        user = self._staff_reports()
        rep = GovernedSavedReport.objects.create(
            school=self.school_a,
            created_by=user,
            name="Detail me",
            definition={"dataset_id": "students", "fields": ["id"], "limit": 5},
        )
        factory = RequestFactory()
        ok_req = factory.get(
            reverse(
                "analytics:governed_saved_report_detail",
                kwargs={"report_id": rep.pk},
            )
        )
        ok_req.user = user
        ok_req.school = self.school_a
        resp_ok = governed_saved_report_detail(ok_req, rep.pk)
        self.assertEqual(resp_ok.status_code, 200)

        bad_req = factory.get(
            reverse(
                "analytics:governed_saved_report_detail",
                kwargs={"report_id": rep.pk},
            )
        )
        bad_req.user = user
        bad_req.school = self.school_b
        with self.assertRaises(Http404):
            governed_saved_report_detail(bad_req, rep.pk)

    def test_governed_report_builder_renders_with_tenant_context(self):
        factory = RequestFactory()
        user = self._staff_reports()
        req = factory.get(reverse("analytics:governed_query_builder"))
        req.user = user
        req.school = self.school_a
        resp = governed_report_builder(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"data-rmc-governed-report-builder", resp.content)
