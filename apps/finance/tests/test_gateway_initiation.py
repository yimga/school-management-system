"""Outbound gateway-collection service (DB-free).

Locks the two safety properties: FAIL-CLOSED + INERT (disabled by default;
unconfigured gateway attempts no charge) and reference-carries-invoice-id so the
inbound webhook can match. The service must never fabricate success.
"""

from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from apps.finance import gateway_initiation as gi
from apps.finance.gateways.base import GatewayResult


class _FakeProfile:
    def __init__(self, currency_code="XAF"):
        self.currency_code = currency_code


class _FakeSchool:
    currency_code = "XAF"


class _FakeInvoice:
    def __init__(self, pk=1, balance=Decimal("100.00"), school=None, currency_code="XAF"):
        self.pk = pk
        self.school = school if school is not None else _FakeSchool()
        self.computed_balance = balance
        self.total_amount = balance
        self.currency = None
        self.profile = _FakeProfile(currency_code)


class ReferenceRoundTripTests(SimpleTestCase):
    def test_invoice_id_round_trips(self):
        ref = gi.build_collection_reference(42)
        self.assertTrue(ref.startswith("rmcinv-42-"))
        self.assertEqual(gi.invoice_id_from_reference(ref), 42)

    def test_bad_references_return_none(self):
        for bad in ("", None, "nope", "rmcinv-abc-x", "other-1-x"):
            self.assertIsNone(gi.invoice_id_from_reference(bad))


class FailClosedTests(SimpleTestCase):
    @override_settings(RMC_GATEWAY_COLLECTION_ENABLED=False)
    def test_disabled_by_default(self):
        result = gi.initiate_invoice_collection(
            invoice=_FakeInvoice(), method_code="MTN_MOMO", policy={}
        )
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response["status"], "collection_disabled")

    @override_settings(RMC_GATEWAY_COLLECTION_ENABLED=True)
    def test_unconfigured_gateway_fails_closed(self):
        # Real MTN gateway, empty policy -> empty config -> not_configured; the
        # gateway refuses and nothing is charged.
        result = gi.initiate_invoice_collection(
            invoice=_FakeInvoice(), method_code="MTN_MOMO", policy={}
        )
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "not_configured")

    @override_settings(RMC_GATEWAY_COLLECTION_ENABLED=True)
    def test_unknown_method_has_no_gateway(self):
        result = gi.initiate_invoice_collection(
            invoice=_FakeInvoice(), method_code="NOT_A_REAL_METHOD", policy={}
        )
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "no_gateway")

    @override_settings(RMC_GATEWAY_COLLECTION_ENABLED=True)
    def test_nothing_due(self):
        result = gi.initiate_invoice_collection(
            invoice=_FakeInvoice(balance=Decimal("0.00")),
            method_code="MTN_MOMO",
            policy={},
        )
        self.assertFalse(result.success)
        self.assertEqual(result.raw_response.get("status"), "nothing_due")


class InitiationHandoffTests(SimpleTestCase):
    @override_settings(RMC_GATEWAY_COLLECTION_ENABLED=True)
    def test_success_passes_amount_currency_and_invoice_reference(self):
        captured = {}

        class _FakeGateway:
            def initiate(self, **kwargs):
                captured.update(kwargs)
                return GatewayResult(
                    success=True, transaction_id="tx1", message="requested"
                )

        original = gi.get_gateway
        gi.get_gateway = lambda school, method_code, policy=None: _FakeGateway()
        try:
            result = gi.initiate_invoice_collection(
                invoice=_FakeInvoice(pk=77, balance=Decimal("2500.00")),
                method_code="MTN_MOMO",
                payer_phone="+237600000000",
                policy={},
            )
        finally:
            gi.get_gateway = original

        self.assertTrue(result.success)
        # Amount is the invoice outstanding balance, currency resolved from profile.
        self.assertEqual(captured["amount"], Decimal("2500.00"))
        self.assertEqual(captured["currency"], "XAF")
        self.assertEqual(captured["payer_phone"], "+237600000000")
        # The reference round-trips the invoice id for the webhook to match.
        self.assertEqual(gi.invoice_id_from_reference(captured["reference"]), 77)
