import hashlib
import hmac
import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import ComplianceProfile, Invoice, InvoiceLine, WebhookLog
from apps.people.models import StudentProfile
from apps.siteconfig.models import Integration


class WebhookDeadLetterTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="DL Test",
            country_code="US",
            currency_code="USD",
            currency_symbol="$",
            timezone="UTC",
            chart_template=ComplianceProfile.ChartTemplate.GENERIC,
            min_wage=Decimal("15"),
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
        self.department = Department.objects.create(name="D", code="DL")
        self.specialty = Specialty.objects.create(
            department=self.department, name="G", code="G"
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="C1",
            code="DLC1",
        )
        self.student = StudentProfile.objects.create(
            first_name="A",
            last_name="B",
            student_code="S-DL",
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
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
            issued_date=timezone.now().date(),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Fee",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            amount=Decimal("100.00"),
            fee_item=None,
        )
        self.secret = "dl-secret"
        Integration.objects.create(
            name="DLProv",
            slug="dl-payments",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "dl_provider",
                "webhook_secret": self.secret,
                "signature_header": "X-Signature",
                "timestamp_header": "X-Timestamp",
            },
        )

    def _sig(self, body: bytes) -> str:
        return hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()

    def test_dead_letter_after_five_failures_same_reference(self):
        ref = "txn-deadletter-xyz"
        # FAILED audit rows never own the idempotency bucket (only the claim row
        # does — the finance_webhooklog_uniq_provider_bucket unique constraint
        # forbids >1 row per (provider, non-empty bucket)). The dead-letter
        # counter keys on reference_id, so repeated failures accumulate with
        # bucket="" — mirror that real shape here.
        for _ in range(5):
            WebhookLog.objects.create(
                provider="dl_provider",
                reference_id=ref,
                idempotency_bucket="",
                client_ip="127.0.0.1",
                status=WebhookLog.Status.FAILED,
            )
        payload = {
            "reference": ref,
            "transaction_id": ref,
            "amount": "100.00",
            "invoice_id": str(self.invoice.id),
        }
        body = json.dumps(payload).encode()
        r = self.client.post(
            reverse("finance:payment_webhook", kwargs={"provider_slug": "dl-payments"}),
            data=body,
            content_type="application/json",
            HTTP_X_SIGNATURE=self._sig(body),
            HTTP_X_TIMESTAMP=str(int(timezone.now().timestamp())),
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("status"), "dead_letter")
        self.assertTrue(
            WebhookLog.objects.filter(
                reference_id=ref, status=WebhookLog.Status.DEAD_LETTER
            ).exists()
        )
