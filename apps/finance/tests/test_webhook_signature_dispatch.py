"""M26 slice 3 — provider-accurate webhook signature dispatch on the LIVE rail.

Two layers:

1. Pure unit tests for :mod:`apps.finance.webhooks.signature_dispatch` (no DB) —
   scheme resolution + per-scheme dispatch + fail-closed on an unknown scheme.

2. End-to-end through ``payment_provider_webhook`` proving:
   * an Integration with NO ``signature_scheme`` still verifies via the historical
     generic HMAC path and posts a Payment (backward-compat — the live default is
     unchanged);
   * an Integration opting into ``signature_scheme="stripe"`` accepts a correct
     Stripe signature (posts a Payment) and rejects a tampered one (403, nothing
     posted).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import ComplianceProfile, Invoice, InvoiceLine, Payment, WebhookLog
from apps.finance.webhooks.signature_dispatch import (
    GENERIC_SCHEME,
    scheme_from_config,
    verify_provider_signature,
)
from apps.people.models import StudentProfile
from apps.siteconfig.models import Integration


class SchemeFromConfigTests(unittest.TestCase):
    def test_absent_key_is_generic(self):
        self.assertEqual(scheme_from_config({}), "")
        self.assertEqual(scheme_from_config(None), "")
        self.assertEqual(scheme_from_config({"webhook_secret": "x"}), "")

    def test_generic_sentinel_is_generic(self):
        self.assertEqual(scheme_from_config({"signature_scheme": GENERIC_SCHEME}), "")
        self.assertEqual(scheme_from_config({"signature_scheme": "GENERIC_HMAC"}), "")

    def test_named_scheme_is_normalized(self):
        self.assertEqual(scheme_from_config({"signature_scheme": "Stripe"}), "stripe")
        self.assertEqual(scheme_from_config({"signature_scheme": " mpesa_daraja "}), "mpesa_daraja")


class VerifyProviderSignatureTests(unittest.TestCase):
    def test_stripe_valid_and_tampered(self):
        secret = "whsec_dispatch_unit"
        body = json.dumps({"id": "evt_1", "invoiceId": 5}).encode()
        ts = int(time.time())
        digest = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        headers = {"Stripe-Signature": f"t={ts},v1={digest}"}
        ok, reason = verify_provider_signature(
            "stripe", headers=headers, raw_body=body, secret=secret
        )
        self.assertTrue(ok, reason)
        # Tampered body -> mismatch.
        ok, reason = verify_provider_signature(
            "stripe", headers=headers, raw_body=body + b" ", secret=secret
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "stripe_signature_mismatch")

    def test_paystack_valid_and_invalid(self):
        secret = "sk_dispatch_unit"
        body = b'{"event":"charge.success"}'
        sig = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
        ok, _ = verify_provider_signature(
            "paystack", headers={"x-paystack-signature": sig}, raw_body=body, secret=secret
        )
        self.assertTrue(ok)
        ok, reason = verify_provider_signature(
            "paystack", headers={"x-paystack-signature": "deadbeef"}, raw_body=body, secret=secret
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "paystack_signature_mismatch")

    def test_flutterwave_uses_secret_hash_from_config(self):
        ok, _ = verify_provider_signature(
            "flutterwave",
            headers={"verif-hash": "FLW_HASH"},
            raw_body=b"",
            secret="",
            config={"flutterwave_secret_hash": "FLW_HASH"},
        )
        self.assertTrue(ok)
        ok, reason = verify_provider_signature(
            "flutterwave",
            headers={"verif-hash": "wrong"},
            raw_body=b"",
            secret="",
            config={"secret_hash": "FLW_HASH"},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "flutterwave_verif_hash_mismatch")

    def test_mpesa_daraja_valid(self):
        secret = "mpesa_dispatch"
        body = b'{"Body":{"stkCallback":{"CheckoutRequestID":"ws_1","ResultCode":0}}}'
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        ok, reason = verify_provider_signature(
            "mpesa_daraja", headers={"X-Signature": sig}, raw_body=body, secret=secret
        )
        self.assertTrue(ok, reason)

    def test_aggregator_hmac_honors_header_name(self):
        secret = "agg_dispatch"
        body = b'{"transaction_id":"abc"}'
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        ok, reason = verify_provider_signature(
            "aggregator_hmac",
            headers={"X-Sig": sig},
            raw_body=body,
            secret=secret,
            config={"signature_header": "X-Sig"},
        )
        self.assertTrue(ok, reason)

    def test_unknown_scheme_fails_closed(self):
        ok, reason = verify_provider_signature(
            "totally_made_up", headers={}, raw_body=b"{}", secret="x"
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown_signature_scheme")


class WebhookSignatureSchemeLiveRailTests(TestCase):
    """End-to-end through payment_provider_webhook."""

    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon",
            country_code="CM",
            currency_code="XAF",
            currency_symbol="XAF",
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
            name="Form 4",
            code="F4",
        )
        self.student = StudentProfile.objects.create(
            first_name="Sig",
            last_name="Scheme",
            student_code="STD-SIG-1",
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

    def _url(self, provider_slug):
        return reverse("finance:payment_webhook", kwargs={"provider_slug": provider_slug})

    def _post(self, provider_slug, body: bytes, **headers):
        return self.client.post(
            self._url(provider_slug),
            data=body,
            content_type="application/json",
            **headers,
        )

    def test_generic_scheme_unset_still_verifies_and_posts(self):
        """Backward-compat: no signature_scheme -> historical generic HMAC path."""
        secret = "generic-unset-secret"
        Integration.objects.create(
            name="MTN Generic",
            slug="mtn-generic",
            provider="payments",
            enabled=True,
            config={"provider_slug": "mtn_momo", "webhook_secret": secret},
        )
        body = json.dumps(
            {
                "invoiceId": self.invoice.pk,
                "amount": "40.00",
                "transaction_id": "generic-tx-1",
                "status": "successful",
            }
        ).encode()
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        resp = self._post("mtn_momo", body, HTTP_X_SIGNATURE=sig)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "ok")
        self.assertTrue(Payment.objects.filter(external_reference="generic-tx-1").exists())

    def test_stripe_scheme_accepts_valid_signature_and_posts(self):
        secret = "whsec_live_rail"
        Integration.objects.create(
            name="Stripe",
            slug="stripe-sig",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "stripe",
                "webhook_secret": secret,
                "signature_scheme": "stripe",
            },
        )
        body = json.dumps(
            {
                "invoiceId": self.invoice.pk,
                "amount": "30.00",
                "transaction_id": "stripe-ok-1",
                "status": "successful",
            }
        ).encode()
        ts = int(time.time())
        digest = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        resp = self._post("stripe", body, HTTP_STRIPE_SIGNATURE=f"t={ts},v1={digest}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "ok")
        payment = Payment.objects.get(external_reference="stripe-ok-1")
        self.assertEqual(payment.amount, Decimal("30.00"))

    def test_stripe_scheme_rejects_tampered_signature(self):
        secret = "whsec_live_rail_2"
        Integration.objects.create(
            name="Stripe Tamper",
            slug="stripe-sig-tamper",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "stripe",
                "webhook_secret": secret,
                "signature_scheme": "stripe",
            },
        )
        body = json.dumps(
            {
                "invoiceId": self.invoice.pk,
                "amount": "30.00",
                "transaction_id": "stripe-bad-1",
                "status": "successful",
            }
        ).encode()
        ts = int(time.time())
        # Sign a DIFFERENT body so the header is well-formed but does not match.
        wrong = hmac.new(secret.encode(), f"{ts}.".encode() + body + b"x", hashlib.sha256).hexdigest()
        resp = self._post("stripe", body, HTTP_STRIPE_SIGNATURE=f"t={ts},v1={wrong}")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Invalid signature", resp.content.decode("utf-8"))
        self.assertFalse(Payment.objects.filter(external_reference="stripe-bad-1").exists())
        log = WebhookLog.objects.filter(
            reference_id="stripe-bad-1", status=WebhookLog.Status.INVALID
        ).latest("created_at")
        self.assertFalse(log.signature_valid)
        self.assertEqual(log.response_status, 403)


if __name__ == "__main__":
    unittest.main()
