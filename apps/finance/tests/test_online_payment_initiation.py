"""M26 slice 2 — the parent-facing online-payment endpoint.

Locks the inert guarantee (route 404s when the flag is off), the fail-closed
handoff to the gateway service (no configured gateway -> JSON ok=False, nothing
settled), and input validation. Auth mirrors upload_payment_receipt.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.accounts.models import User
from apps.finance.models import ComplianceProfile, Invoice
from apps.people.models import StudentProfile


class OnlinePaymentInitiationTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon",
            country_code="CM",
            currency_code="XAF",
            currency_symbol="FCFA",
            timezone="Africa/Douala",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.department = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(
            department=self.department, name="General", code="GEN"
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 3",
            code="F3",
        )
        self.student = StudentProfile.objects.create(
            first_name="Abajo",
            last_name="Jeffter",
            student_code="STU-001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        self.user = User.objects.create_superuser(
            username="superadmin", password="Pass_1234", email="s@example.com"
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal("25000.00"),
            balance_amount=Decimal("25000.00"),
            issued_date="2026-02-01",
        )
        self.client.login(username="superadmin", password="Pass_1234")

    def _url(self):
        return reverse("finance:initiate_online_payment", args=[self.invoice.id])

    @override_settings(RMC_GATEWAY_COLLECTION_ENABLED=False)
    def test_route_404s_when_flag_off(self):
        # Inert in production: the endpoint does not exist until enabled.
        response = self.client.post(self._url(), {"method_code": "MTN_MOMO"})
        self.assertEqual(response.status_code, 404)

    @override_settings(RMC_GATEWAY_COLLECTION_ENABLED=True)
    def test_missing_method_code_is_rejected(self):
        response = self.client.post(self._url(), {})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    @override_settings(RMC_GATEWAY_COLLECTION_ENABLED=True)
    def test_unconfigured_gateway_fails_closed_and_settles_nothing(self):
        response = self.client.post(
            self._url(),
            {"method_code": "MTN_MOMO", "payer_phone": "+237600000000"},
        )
        # No credentials configured -> the gateway/service refuses; JSON ok=False.
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["ok"])
        # Nothing was recorded — settlement is webhook-only.
        self.assertEqual(self.invoice.payments.count(), 0)

    @override_settings(RMC_GATEWAY_COLLECTION_ENABLED=True)
    def test_ui_form_post_redirects_with_message(self):
        # The invoice-page form posts _ui=1 -> message + redirect (not raw JSON).
        response = self.client.post(
            self._url(),
            {"method_code": "MTN_MOMO", "payer_phone": "+237600000000", "_ui": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.invoice.payments.count(), 0)


class OnlinePaymentInvoicePageTests(OnlinePaymentInitiationTests):
    """The invoice detail page shows the 'Pay online' form only when enabled."""

    def _detail(self):
        return self.client.get(
            reverse("finance:invoice_detail", args=[self.invoice.id])
        )

    @override_settings(RMC_GATEWAY_COLLECTION_ENABLED=True)
    def test_form_shown_when_enabled(self):
        response = self._detail()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="online-payment-form"')

    @override_settings(RMC_GATEWAY_COLLECTION_ENABLED=False)
    def test_form_hidden_when_disabled(self):
        response = self._detail()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="online-payment-form"')
