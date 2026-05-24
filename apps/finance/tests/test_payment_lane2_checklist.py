"""Lane 2 operator checklist contract tests (SFDP Phase 2)."""

from django.test import SimpleTestCase

from apps.finance.payment_lane2_checklist import (
    COUNSEL_BLOCKED_FEATURES,
    DEFERRED_V1_PSP_SLUGS,
    LANE2_PILOT_CORRIDORS,
    get_lane2_checklist,
    lane2_matrix_for_operator,
)


class PaymentLane2ChecklistTests(SimpleTestCase):
    def test_pilot_corridors_cover_register_ids(self):
        ids = {row.register_id for row in LANE2_PILOT_CORRIDORS}
        self.assertIn("stripe_global_cards", ids)
        self.assertIn("stripe_connect_platform", ids)
        self.assertIn("paystack_wa", ids)
        self.assertIn("flutterwave_multi_country", ids)
        self.assertIn("mtn_momo", ids)
        self.assertIn("orange_money", ids)

    def test_get_lane2_checklist_hit(self):
        row = get_lane2_checklist("paystack_wa")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.psp_slug, "paystack")
        self.assertIn("NG", row.corridors)

    def test_operator_matrix_serializable(self):
        matrix = lane2_matrix_for_operator()
        self.assertGreaterEqual(len(matrix), 6)
        self.assertTrue(all("evidence_path" in row for row in matrix))

    def test_deferred_and_counsel_sets(self):
        self.assertIn("razorpay", DEFERRED_V1_PSP_SLUGS)
        self.assertIn("paystack_subaccounts", COUNSEL_BLOCKED_FEATURES)
        self.assertIn("desk_to_desk_client_replication_mesh", COUNSEL_BLOCKED_FEATURES)
