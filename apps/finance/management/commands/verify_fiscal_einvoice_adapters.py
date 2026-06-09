from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.finance.fiscal_einvoice import (
    BrazilNFeAdapter,
    FiscalInvoiceDocument,
    FiscalLine,
    FiscalParty,
    MexicoCFDIAdapter,
)


class Command(BaseCommand):
    help = "Verify deterministic CFDI and NF-e provider payload construction."

    def handle(self, *args, **options):
        document = FiscalInvoiceDocument(
            jurisdiction="test",
            invoice_reference="INV-1",
            issued_at="2026-06-09T12:00:00",
            currency_code="MXN",
            issuer=FiscalParty("AAA010101AAA", "School", "01000", "601"),
            customer=FiscalParty("XAXX010101000", "Family", "01000", "616"),
            lines=(FiscalLine("Tuition", Decimal("1"), Decimal("100"), Decimal("100")),),
            subtotal=Decimal("100"),
            tax_amount=Decimal("0"),
            total=Decimal("100"),
        )
        cfdi = MexicoCFDIAdapter().build_unsigned_payload(document)
        nfe = BrazilNFeAdapter().build_unsigned_payload(document)
        if "Comprobante" not in cfdi or "NFe-4.00-provider-envelope" not in nfe:
            raise RuntimeError("fiscal adapter verification failed")
        self.stdout.write(self.style.SUCCESS("Fiscal e-invoice adapters verified."))
