import hashlib
import hmac
import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import ComplianceProfile, Invoice, InvoiceLine, Payment, PaymentMethodCode, WebhookLog
from apps.people.models import StudentProfile
from apps.siteconfig.models import Integration


class MobileMoneyWebhookContractTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon",
            country_code="CM",
            currency_code="XAF",
            currency_symbol="XAF",
            timezone="Africa/Douala",
            chart_template=ComplianceProfile.ChartTemplate.OHADA,
            min_wage=Decimal("60000"),
            default_hours_per_week=Decimal("40"),
            overtime_multiplier=Decimal("1.5"),
            annual_leave_days=21,
            maternity_leave_days=84,
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.department = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(department=self.department, name="General", code="GEN")
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 2",
            code="F2",
        )
        self.student = StudentProfile.objects.create(
            first_name="Webhook",
            last_name="Student",
            student_code="STD-WEBHOOK-1",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal("200.00"),
            balance_amount=Decimal("200.00"),
            issued_date=timezone.now().date(),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=Decimal("200.00"),
            amount=Decimal("200.00"),
            fee_item=None,
        )

    @staticmethod
    def _signature(secret: str, raw_body: bytes) -> str:
        return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()

    def _post_webhook(
        self,
        *,
        provider_slug: str,
        payload: dict,
        secret: str,
        signature_header: str = "X-Signature",
        signature_prefix: str = "",
    ):
        raw_body = json.dumps(payload).encode("utf-8")
        signature = self._signature(secret, raw_body)
        if signature_prefix:
            signature = f"{signature_prefix}={signature}"
        header_key = f"HTTP_{signature_header.upper().replace('-', '_')}"
        return self.client.post(
            reverse("finance:payment_webhook", kwargs={"provider_slug": provider_slug}),
            data=raw_body,
            content_type="application/json",
            **{header_key: signature},
        )

    def test_mtn_contract_accepts_invoice_id_and_transaction_id(self):
        secret = "mtn-secret"
        Integration.objects.create(
            name="MTN",
            slug="mtn-payments",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "mtn_momo",
                "webhook_secret": secret,
            },
        )

        response = self._post_webhook(
            provider_slug="mtn_momo",
            secret=secret,
            payload={
                "provider": "mtn",
                "invoiceId": self.invoice.pk,
                "amount": "50.00",
                "transaction_id": "mtn-tx-001",
                "status": "successful",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")
        payment = Payment.objects.get(external_reference="mtn-tx-001")
        self.assertEqual(payment.method, PaymentMethodCode.MTN_MOMO)
        self.assertEqual(payment.amount, Decimal("50.00"))
        self.assertTrue(WebhookLog.objects.filter(provider="mtn_momo", reference_id="mtn-tx-001").exists())

    def test_orange_contract_accepts_alias_slug_and_prefixed_signature(self):
        secret = "orange-secret"
        Integration.objects.create(
            name="Orange",
            slug="orange-payments",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "orange_momo",
                "webhook_secret": secret,
            },
        )

        response = self._post_webhook(
            provider_slug="orange_money",
            secret=secret,
            signature_prefix="sha256",
            payload={
                "invoice": self.invoice.pk,
                "amount": "25.00",
                "payment_reference": "orange-ref-1",
                "status": "completed",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")
        payment = Payment.objects.get(external_reference="orange-ref-1")
        self.assertEqual(payment.method, PaymentMethodCode.ORANGE_MOMO)
        self.assertEqual(payment.amount, Decimal("25.00"))

    def test_duplicate_detection_is_shared_across_orange_aliases(self):
        secret = "orange-secret-dup"
        Integration.objects.create(
            name="Orange",
            slug="orange-payments-dup",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "orange_momo",
                "webhook_secret": secret,
            },
        )

        payload = {
            "invoice": self.invoice.pk,
            "amount": "10.00",
            "payment_reference": "orange-dup-1",
            "status": "completed",
        }
        first = self._post_webhook(provider_slug="orange_money", payload=payload, secret=secret)
        second = self._post_webhook(provider_slug="orange_momo", payload=payload, secret=secret)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json().get("status"), "ignored")
        self.assertEqual(Payment.objects.filter(external_reference="orange-dup-1").count(), 1)
