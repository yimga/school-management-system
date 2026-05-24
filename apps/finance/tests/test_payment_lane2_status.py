"""Lane 2 status rollup tests (SFDP 1436)."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.finance.payment_lane2_status import build_lane2_corridor_rows


class PaymentLane2StatusTests(SimpleTestCase):
    @patch("apps.finance.payment_lane2_status.get_payment_integration_by_slug", return_value=None)
    def test_build_lane2_rows_includes_stripe_and_paystack(self, _mock_integ):
        rows = build_lane2_corridor_rows(school=None)
        register_ids = {r["register_id"] for r in rows}
        self.assertIn("stripe_global_cards", register_ids)
        self.assertIn("stripe_connect_platform", register_ids)
        self.assertIn("paystack_wa", register_ids)
        self.assertFalse(any(r["live_proof"] for r in rows))

    @patch("apps.finance.payment_lane2_status.get_payment_integration_by_slug", return_value=None)
    def test_engine_labels(self, _mock_integ):
        rows = build_lane2_corridor_rows()
        engines = {r["register_id"]: r["engine"] for r in rows}
        self.assertEqual(engines["stripe_global_cards"], "platform")
        self.assertEqual(engines["paystack_wa"], "tuition")
