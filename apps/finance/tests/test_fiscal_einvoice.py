from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.fiscal_einvoice import (
    BrazilNFeAdapter,
    FiscalInvoiceDocument,
    FiscalInvoiceError,
    FiscalLine,
    FiscalParty,
    MexicoCFDIAdapter,
)


def _document():
    return FiscalInvoiceDocument(
        jurisdiction="MX",
        invoice_reference="INV-42",
        issued_at="2026-06-09T12:00:00",
        currency_code="MXN",
        issuer=FiscalParty("AAA010101AAA", "School", "01000", "601"),
        customer=FiscalParty("XAXX010101000", "Family", "01000", "616"),
        lines=(FiscalLine("Tuition", Decimal("1"), Decimal("100"), Decimal("100")),),
        subtotal=Decimal("100"),
        tax_amount=Decimal("16"),
        total=Decimal("116"),
    )


class FiscalEInvoiceAdapterTests(SimpleTestCase):
    def test_cfdi_payload_contains_required_parties_and_totals(self):
        payload = MexicoCFDIAdapter().build_unsigned_payload(_document())
        self.assertIn('Version="4.0"', payload)
        self.assertIn('Rfc="AAA010101AAA"', payload)
        self.assertIn('Total="116.00"', payload)

    def test_nfe_provider_envelope_is_deterministic(self):
        adapter = BrazilNFeAdapter()
        self.assertEqual(
            adapter.build_unsigned_payload(_document()),
            adapter.build_unsigned_payload(_document()),
        )

    def test_submission_fails_closed_without_signing_and_transport(self):
        with self.assertRaises(FiscalInvoiceError):
            MexicoCFDIAdapter().submit(_document())

    def test_submission_passes_idempotency_key_to_provider(self):
        seen = {}

        def transport(**kwargs):
            seen.update(kwargs)
            return {"accepted": True, "status": "stamped", "external_reference": "X1"}

        result = MexicoCFDIAdapter().submit(
            _document(),
            signer=lambda payload: "signed:" + payload,
            transport=transport,
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.external_reference, "X1")
        self.assertEqual(len(seen["idempotency_key"]), 64)
