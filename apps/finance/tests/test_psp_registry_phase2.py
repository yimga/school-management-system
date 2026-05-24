"""PSP registry Phase 2 deferred rows (planned, not live)."""

from django.test import SimpleTestCase

from apps.billing.psp_adapter_registry import get_psp


class PSPRegistryPhase2Tests(SimpleTestCase):
    def test_global_psps_in_progress(self):
        for slug in ("razorpay", "pesapal", "mercado_pago", "dlocal"):
            row = get_psp(slug)
            self.assertIsNotNone(row, slug)
            assert row is not None
            self.assertEqual(row.adapter_status, "in_progress", slug)

    def test_pilot_corridors_in_progress(self):
        for slug in ("paystack", "flutterwave", "mtn_momo", "orange_money"):
            row = get_psp(slug)
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row.adapter_status, "in_progress")
