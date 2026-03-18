from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentMethodCode,
)
from apps.people.models import StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.models import default_backend_feature_flags


class MinistryPlaceholderApiTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff_ministry",
            password="pass1234",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.force_login(self.staff)

        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        department = Department.objects.create(name="Technical", code="TECH-API")
        specialty = Specialty.objects.create(
            department=department, name="ICT", code="ICT-API"
        )
        classroom = Classroom.objects.create(
            academic_year=self.year,
            department=department,
            name="Form 4",
            code="F4-API",
        )
        self.student = StudentProfile.objects.create(
            first_name="Nana",
            last_name="Acha",
            student_code="S-API-001",
            academic_year=self.year,
            classroom=classroom,
            specialty=specialty,
            exam_candidate_number="GCE123",
            exam_system="GCE",
            is_active=True,
        )

        self.profile = ComplianceProfile.objects.create(
            name="CMR Profile",
            country_code="CM",
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            student=self.student,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.PARTIAL,
            issued_date=date(2026, 1, 10),
            due_date=date(2026, 1, 31),
            total_amount=Decimal("50000.00"),
            balance_amount=Decimal("25000.00"),
            reference="INV-CMR-001",
            payment_code="PAY-CMR-001",
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1.00"),
            unit_price=Decimal("50000.00"),
            amount=Decimal("50000.00"),
        )
        Payment.objects.create(
            invoice=self.invoice,
            student=self.student,
            amount=Decimal("25000.00"),
            method=PaymentMethodCode.MTN_MOMO,
            status="completed",
            paid_at=date(2026, 1, 12),
            reference="TXN-001",
        )

        site = get_platform_site_settings_record(create=True)
        flags = {
            **default_backend_feature_flags(),
            **(site.backend_feature_flags or {}),
        }
        flags["enable_ministry_api_cartescolaire"] = True
        flags["enable_ministry_api_dgi"] = True
        flags["enable_ministry_live_sync"] = True
        site.backend_feature_flags = flags
        site.school_code = "GIL"
        site.save(update_fields=["backend_feature_flags", "school_code"])

    def test_cartescolaire_placeholder_returns_registry_data(self):
        response = self.client.get("/api/ministry/cartescolaire/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["export_type"], "cartescolaire")
        self.assertEqual(payload["record_count"], 1)
        self.assertEqual(payload["records"][0]["student_code"], "S-API-001")
        self.assertIn("integration_runtime", payload)
        self.assertIn("sync", payload)
        self.assertFalse(payload["sync"]["attempted"])

    def test_dgi_placeholder_returns_finance_summary(self):
        response = self.client.get("/api/ministry/dgi/?start=2026-01-01&end=2026-01-31")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["export_type"], "dgi")
        self.assertEqual(payload["summary"]["invoice_count"], 1)
        self.assertEqual(payload["summary"]["payment_count"], 1)
        self.assertGreaterEqual(payload["summary"]["estimated_stamp_duty_xaf"], 1000.0)
        self.assertIn("integration_runtime", payload)
        self.assertIn("sync", payload)
        self.assertFalse(payload["sync"]["attempted"])

    def test_sync_query_uses_connector_in_mock_mode(self):
        response = self.client.get(
            "/api/ministry/dgi/?start=2026-01-01&end=2026-01-31&sync=1"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["sync"]["attempted"])
        self.assertEqual(payload["sync"]["result"]["mode"], "mock")
        self.assertFalse(payload["sync"]["result"]["attempted"])

    def test_disabled_flag_returns_503(self):
        site = get_platform_site_settings_record(create=True)
        flags = dict(site.backend_feature_flags or {})
        flags["enable_ministry_api_dgi"] = False
        site.backend_feature_flags = flags
        site.save(update_fields=["backend_feature_flags"])

        response = self.client.get("/api/ministry/dgi/")
        self.assertEqual(response.status_code, 503)

    def test_cartescolaire_rate_limit_returns_429(self):
        with patch(
            "apps.api.ministry_placeholders.throttle_ip_request",
            return_value=(False, 900),
        ):
            response = self.client.get("/api/ministry/cartescolaire/")
        self.assertEqual(response.status_code, 429)
        payload = response.json()
        self.assertEqual(payload.get("status"), "rate_limited")
        self.assertEqual(payload.get("service"), "cartescolaire")

    def test_dgi_rate_limit_returns_429(self):
        with patch(
            "apps.api.ministry_placeholders.throttle_ip_request",
            return_value=(False, 900),
        ):
            response = self.client.get("/api/ministry/dgi/")
        self.assertEqual(response.status_code, 429)
        payload = response.json()
        self.assertEqual(payload.get("status"), "rate_limited")
        self.assertEqual(payload.get("service"), "dgi")
