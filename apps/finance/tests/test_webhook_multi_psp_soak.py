"""Multi-PSP webhook soak — Paystack + Flutterwave + MTN share exactly-once posting.

Extends the MTN-only soak (``test_webhook_duplicate_soak``) across three rails
on the live ``payment_webhook`` path with mocked secrets (no merchant sandbox).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    Payment,
    WebhookLog,
)
from apps.people.models import StudentProfile
from apps.siteconfig.models import Integration


class MultiPspWebhookSoakTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Multi PSP Soak",
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
        self.department = Department.objects.create(name="Science", code="SCI-MP")
        self.specialty = Specialty.objects.create(
            department=self.department, name="General", code="GEN-MP"
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 2",
            code="F2-MP",
        )
        self.student = StudentProfile.objects.create(
            first_name="Multi",
            last_name="PSP",
            student_code="STD-MPSP-1",
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
            total_amount=Decimal("300.00"),
            balance_amount=Decimal("300.00"),
            issued_date=timezone.now().date(),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=Decimal("300.00"),
            amount=Decimal("300.00"),
            fee_item=None,
        )
        self.secrets = {
            "paystack": "psk-soak-secret",
            "flutterwave": "flw-soak-secret",
            "mtn_momo": "mtn-soak-secret",
        }
        for slug, secret in self.secrets.items():
            Integration.objects.create(
                name=f"{slug} Soak",
                slug=f"{slug}-payments-soak",
                provider="payments",
                enabled=True,
                config={"provider_slug": slug, "webhook_secret": secret},
            )

    def _post(self, provider_slug: str, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        secret = self.secrets[provider_slug]
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            reverse(
                "finance:payment_webhook", kwargs={"provider_slug": provider_slug}
            ),
            data=body,
            content_type="application/json",
            HTTP_X_SIGNATURE=signature,
        )

    def _assert_exactly_once(self, *, provider: str, tx_id: str, amount: Decimal):
        self.assertEqual(
            Payment.objects.filter(external_reference=tx_id).count(),
            1,
            msg=f"{provider} posted more/less than once for {tx_id}",
        )
        processed = WebhookLog.objects.filter(
            provider=provider, status=WebhookLog.Status.PROCESSED
        )
        self.assertEqual(processed.filter(reference_id=tx_id).count(), 1)

    def test_three_rails_each_replay_exactly_once(self):
        cases = [
            (
                "paystack",
                "psk-multi-1",
                {
                    "event": "charge.success",
                    "invoiceId": self.invoice.pk,
                    "amount": "50.00",
                    "transaction_id": "psk-multi-1",
                    "status": "successful",
                    "data": {
                        "reference": "psk-multi-1",
                        "status": "success",
                        "amount": 5000,
                        "currency": "NGN",
                        "metadata": {"invoice_id": self.invoice.pk},
                    },
                },
            ),
            (
                "flutterwave",
                "flw-multi-1",
                {
                    "event": "charge.completed",
                    "invoiceId": self.invoice.pk,
                    "amount": "50.00",
                    "transaction_id": "flw-multi-1",
                    "status": "successful",
                    "data": {
                        "tx_ref": "flw-multi-1",
                        "status": "successful",
                        "amount": 50,
                        "currency": "XAF",
                        "meta": {"invoice_id": self.invoice.pk},
                    },
                },
            ),
            (
                "mtn_momo",
                "mtn-multi-1",
                {
                    "provider": "mtn",
                    "invoiceId": self.invoice.pk,
                    "amount": "50.00",
                    "transaction_id": "mtn-multi-1",
                    "status": "successful",
                },
            ),
        ]
        for slug, tx_id, payload in cases:
            first = self._post(slug, payload)
            second = self._post(slug, payload)
            self.assertEqual(first.status_code, 200, msg=slug)
            self.assertEqual(first.json().get("status"), "ok", msg=slug)
            self.assertEqual(second.status_code, 200, msg=slug)
            self.assertEqual(second.json().get("status"), "ignored", msg=slug)
            self._assert_exactly_once(
                provider=slug, tx_id=tx_id, amount=Decimal("50.00")
            )

        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 3)
        total = Payment.objects.filter(invoice=self.invoice).aggregate(
            total=Sum("amount")
        )["total"]
        self.assertEqual(total, Decimal("150.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_amount, Decimal("150.00"))
