"""Offline payment-intent idempotency (OFFLINE-006 fail-safe).

Covers the partial-unique constraint, the schema_repair dedupe heal, and the
_apply_payment_receipt idempotency path so concurrent offline replay of one
captured payment can never create two intents for one invoice.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile, Invoice, OfflinePaymentIntent
from apps.finance.schema_repair import ensure_offlinepaymentintent_client_id_index
from apps.platform_runtime.offline_queue import _apply_payment_receipt

_INDEX = "uniq_offlinepaymentintent_invoice_client_id"


class OfflinePaymentIntentDedupTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.profile = ComplianceProfile.objects.create(
            name=f"P {uid}", country_code="CM"
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
        )
        self.invoice2 = Invoice.objects.create(
            profile=self.profile,
            total_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
        )
        self.user = User.objects.create_user(username=f"opi_{uid}", password="pw")

    def _mk(self, invoice, key):
        return OfflinePaymentIntent.objects.create(
            invoice=invoice, amount=Decimal("10.00"), client_offline_id=key
        )

    def test_constraint_blocks_duplicate_key_same_invoice(self):
        self._mk(self.invoice, "k1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._mk(self.invoice, "k1")

    def test_constraint_allows_same_key_different_invoice(self):
        self._mk(self.invoice, "k1")
        # Different invoice, same client key — legitimately distinct.
        self._mk(self.invoice2, "k1")
        self.assertEqual(
            OfflinePaymentIntent.objects.filter(client_offline_id="k1").count(), 2
        )

    def test_constraint_allows_multiple_empty_keys(self):
        # Keyless captures carry no constraint — never rejected (offline stays usable).
        self._mk(self.invoice, "")
        self._mk(self.invoice, "")
        self.assertEqual(
            OfflinePaymentIntent.objects.filter(
                invoice=self.invoice, client_offline_id=""
            ).count(),
            2,
        )

    def test_schema_repair_dedupes_existing_and_is_idempotent(self):
        # Drop the index so we can fabricate the pre-fix duplicate state.
        with connection.cursor() as cursor:
            cursor.execute(f'DROP INDEX IF EXISTS "{_INDEX}";')
        a = self._mk(self.invoice, "dup")
        b = self._mk(self.invoice, "dup")  # allowed now (no index)
        self.assertEqual(
            OfflinePaymentIntent.objects.filter(
                invoice=self.invoice, client_offline_id="dup"
            ).count(),
            2,
        )

        self.assertTrue(ensure_offlinepaymentintent_client_id_index())

        # Oldest (min id) keeps the key; the other is blanked — neither deleted.
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.client_offline_id, "dup")
        self.assertEqual(b.client_offline_id, "")
        self.assertEqual(OfflinePaymentIntent.objects.count(), 2)

        # Index now enforces; idempotent re-run is a clean no-op.
        self.assertTrue(ensure_offlinepaymentintent_client_id_index())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._mk(self.invoice, "dup")

    def test_apply_payment_receipt_is_idempotent(self):
        key = f"cap-{uuid.uuid4().hex[:8]}"
        payload = {
            "invoice_id": self.invoice.pk,
            "amount": "25.00",
            "payment_method": "OTHER",
            "client_offline_id": key,
        }
        r1 = _apply_payment_receipt(self.invoice.school_id, self.user.pk, payload)
        r2 = _apply_payment_receipt(self.invoice.school_id, self.user.pk, payload)
        self.assertTrue(r1["ok"])
        self.assertTrue(r2["ok"])
        self.assertEqual(r1["intent_id"], r2["intent_id"])
        self.assertTrue(r2.get("dedup"))
        self.assertEqual(
            OfflinePaymentIntent.objects.filter(
                invoice=self.invoice, client_offline_id=key
            ).count(),
            1,
        )
