from django.test import SimpleTestCase

from apps.finance.models import PaymentMethodCode
from apps.finance.services import PROVIDER_SLUG_TO_METHOD


class PaymentMethodCoverageTests(SimpleTestCase):
    def test_local_first_manual_and_digital_payment_families_are_explicit(self):
        codes = set(PaymentMethodCode.values)
        self.assertTrue(
            {
                "CASH", "BANK", "CARD", "DIRECT_DEBIT", "CHECK", "WALLET",
                "MTN_MOMO", "ORANGE_MOMO", "MPESA", "USSD", "QR", "VOUCHER", "OTHER",
            }.issubset(codes)
        )

    def test_mpesa_is_not_collapsed_into_other(self):
        self.assertEqual(PROVIDER_SLUG_TO_METHOD["mpesa"], PaymentMethodCode.MPESA)
