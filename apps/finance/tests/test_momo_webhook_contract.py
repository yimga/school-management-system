import hashlib
import hmac
import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentMethodCode,
    WebhookLog,
)
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
        self.specialty = Specialty.objects.create(
            department=self.department, name="General", code="GEN"
        )
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
        payload: dict | list | None = None,
        secret: str,
        signature_header: str = "X-Signature",
        signature_prefix: str = "",
        signature_override: str | None = None,
        timestamp_header: str | None = None,
        timestamp_value: str | int | None = None,
        content_type: str = "application/json",
        raw_body: bytes | None = None,
        idempotency_key: str | None = None,
    ):
        encoded_body = (
            raw_body if raw_body is not None else json.dumps(payload).encode("utf-8")
        )
        signature = self._signature(secret, encoded_body)
        if signature_prefix:
            signature = f"{signature_prefix}={signature}"
        if signature_override is not None:
            signature = signature_override
        header_key = f"HTTP_{signature_header.upper().replace('-', '_')}"
        headers = {header_key: signature}
        if timestamp_header:
            ts_key = f"HTTP_{timestamp_header.upper().replace('-', '_')}"
            headers[ts_key] = str(timestamp_value or "")
        if idempotency_key:
            headers["HTTP_IDEMPOTENCY_KEY"] = idempotency_key
        return self.client.post(
            reverse("finance:payment_webhook", kwargs={"provider_slug": provider_slug}),
            data=encoded_body,
            content_type=content_type,
            **headers,
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
        webhook_log = WebhookLog.objects.get(
            provider="mtn_momo", reference_id="mtn-tx-001"
        )
        self.assertEqual(webhook_log.status, WebhookLog.Status.PROCESSED)
        self.assertTrue(webhook_log.signature_valid)
        self.assertEqual(webhook_log.response_status, 200)
        self.assertEqual(webhook_log.payment, payment)
        self.assertIn('"transaction_id": "mtn-tx-001"', webhook_log.request_body)

    def test_mtn_duplicate_when_same_idempotency_key_even_if_transaction_id_differs(
        self,
    ):
        """Idempotency-Key dedup must not depend on payload transaction_id alone (batch 15 #143)."""
        secret = "mtn-secret-idem"
        Integration.objects.create(
            name="MTN Idem",
            slug="mtn-payments-idem",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "mtn_momo",
                "webhook_secret": secret,
            },
        )
        base = {
            "provider": "mtn",
            "invoiceId": self.invoice.pk,
            "amount": "50.00",
            "status": "successful",
        }
        idem = "batch15-shared-idempotency-key"
        first = self._post_webhook(
            provider_slug="mtn_momo",
            secret=secret,
            idempotency_key=idem,
            payload={**base, "transaction_id": "mtn-tx-idem-a"},
        )
        second = self._post_webhook(
            provider_slug="mtn_momo",
            secret=secret,
            idempotency_key=idem,
            payload={**base, "transaction_id": "mtn-tx-idem-b"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json().get("status"), "ok")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json().get("status"), "ignored")
        self.assertEqual(
            Payment.objects.filter(invoice=self.invoice, method=PaymentMethodCode.MTN_MOMO).count(),
            1,
        )
        processed = WebhookLog.objects.get(
            provider="mtn_momo", reference_id="mtn-tx-idem-a", status=WebhookLog.Status.PROCESSED
        )
        self.assertEqual(processed.idempotency_bucket, f"idempotency:{idem}")

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
        first = self._post_webhook(
            provider_slug="orange_money", payload=payload, secret=secret
        )
        second = self._post_webhook(
            provider_slug="orange_momo", payload=payload, secret=secret
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json().get("status"), "ignored")
        self.assertEqual(
            Payment.objects.filter(external_reference="orange-dup-1").count(), 1
        )
        duplicate_log = WebhookLog.objects.filter(
            provider="orange_momo",
            reference_id="orange-dup-1",
            status=WebhookLog.Status.DUPLICATE,
        ).latest("created_at")
        self.assertTrue(duplicate_log.signature_valid)
        self.assertEqual(duplicate_log.response_status, 200)

    def test_mtn_contract_rejects_stale_timestamp_when_required(self):
        secret = "mtn-ts-secret"
        Integration.objects.create(
            name="MTN Timestamp",
            slug="mtn-payments-ts",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "mtn_momo",
                "webhook_secret": secret,
                "require_timestamp": True,
                "timestamp_header": "X-Timestamp",
                "timestamp_tolerance_seconds": 30,
            },
        )
        stale_ts = int(timezone.now().timestamp()) - 120
        response = self._post_webhook(
            provider_slug="mtn_momo",
            secret=secret,
            timestamp_header="X-Timestamp",
            timestamp_value=stale_ts,
            payload={
                "provider": "mtn",
                "invoiceId": self.invoice.pk,
                "amount": "20.00",
                "transaction_id": "mtn-stale-001",
                "status": "successful",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Invalid timestamp", response.content.decode("utf-8"))
        self.assertFalse(
            Payment.objects.filter(external_reference="mtn-stale-001").exists()
        )
        webhook_log = WebhookLog.objects.get(
            provider="mtn_momo", reference_id="mtn-stale-001"
        )
        self.assertEqual(webhook_log.status, WebhookLog.Status.INVALID)
        self.assertTrue(webhook_log.signature_valid)
        self.assertEqual(webhook_log.response_status, 403)
        self.assertIn('"transaction_id": "mtn-stale-001"', webhook_log.request_body)

    def test_orange_contract_rejects_tampered_prefixed_signature(self):
        secret = "orange-secret-tamper"
        Integration.objects.create(
            name="Orange Tamper",
            slug="orange-payments-tamper",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "orange_money",
                "webhook_secret": secret,
            },
        )
        response = self._post_webhook(
            provider_slug="orange_money",
            secret=secret,
            signature_prefix="sha256",
            signature_override="sha256=deadbeef",
            payload={
                "invoice": self.invoice.pk,
                "amount": "15.00",
                "payment_reference": "orange-tamper-1",
                "status": "completed",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Invalid signature", response.content.decode("utf-8"))
        self.assertFalse(
            Payment.objects.filter(external_reference="orange-tamper-1").exists()
        )
        webhook_log = WebhookLog.objects.get(
            provider="orange_momo", reference_id="orange-tamper-1"
        )
        self.assertEqual(webhook_log.status, WebhookLog.Status.INVALID)
        self.assertFalse(webhook_log.signature_valid)
        self.assertEqual(webhook_log.response_status, 403)
        self.assertIn(
            '"payment_reference": "orange-tamper-1"', webhook_log.request_body
        )

    def test_webhook_rejects_non_json_content_type(self):
        secret = "mtn-type-secret"
        Integration.objects.create(
            name="MTN Content Type",
            slug="mtn-payments-content-type",
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
            content_type="text/plain",
            payload={
                "invoiceId": self.invoice.pk,
                "amount": "50.00",
                "transaction_id": "mtn-type-001",
                "status": "successful",
            },
        )

        self.assertEqual(response.status_code, 415)
        self.assertIn("application/json", response.content.decode("utf-8"))
        self.assertFalse(
            Payment.objects.filter(external_reference="mtn-type-001").exists()
        )
        webhook_log = WebhookLog.objects.get(
            provider="mtn_momo", reference_id="unknown"
        )
        self.assertEqual(webhook_log.status, WebhookLog.Status.INVALID)
        self.assertEqual(webhook_log.response_status, 415)
        self.assertIn("Unsupported content type", webhook_log.error_message)

    def test_webhook_rejects_non_object_json_body(self):
        secret = "mtn-array-secret"
        Integration.objects.create(
            name="MTN Array Payload",
            slug="mtn-payments-array-payload",
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
            raw_body=json.dumps(["not", "an", "object"]).encode("utf-8"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON object", response.content.decode("utf-8"))
        self.assertFalse(Payment.objects.exists())
        webhook_log = WebhookLog.objects.get(
            provider="mtn_momo", reference_id="unknown"
        )
        self.assertEqual(webhook_log.status, WebhookLog.Status.INVALID)
        self.assertEqual(webhook_log.response_status, 400)
        self.assertEqual(
            webhook_log.error_message, "Webhook payload must be a JSON object"
        )
