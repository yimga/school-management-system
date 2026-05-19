"""VAT percent vs fraction semantics for regional tax."""

from decimal import Decimal
from unittest import TestCase

from apps.finance.tax_engine import (
    compute_tax,
    resolve_vat_rate_fraction,
    vat_percent_to_fraction,
)


class TaxEngineGlocalTests(TestCase):
    def test_vat_percent_to_fraction(self):
        self.assertEqual(vat_percent_to_fraction(Decimal("19.25")), Decimal("0.1925"))

    def test_resolve_prefers_profile_percent(self):
        rate = resolve_vat_rate_fraction(
            region_code="GB",
            vat_percent=Decimal("19.25"),
        )
        self.assertEqual(rate, Decimal("0.1925"))

    def test_compute_tax_with_percent_profile(self):
        tax = compute_tax(
            Decimal("100.00"),
            "GB",
            rate_override=vat_percent_to_fraction(Decimal("20")),
        )
        self.assertEqual(tax, Decimal("20.00"))
