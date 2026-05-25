"""Runtime tests for apps.finance.permission_to_pay (batch 1493)."""

from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.payment_rail_adapter import register_manual_fallback, registry
from apps.finance.permission_to_pay import (
    PermissionToPayError,
    authorize_payment,
    open_request,
    record_guardian_approval,
)


class PermissionToPayRuntimeTests(SimpleTestCase):
    def setUp(self) -> None:
        registry().clear()
        register_manual_fallback()

    def test_open_below_threshold_skips_guardian(self) -> None:
        req = open_request(
            tenant_id="t1",
            student_id="s1",
            event_code="science-trip",
            amount=Decimal("5.00"),
            currency="USD",
            guardian_threshold=Decimal("10.00"),
        )
        self.assertFalse(req.requires_guardian_approval)
        self.assertEqual(req.state, "ready_to_pay")

    def test_open_above_threshold_needs_guardian(self) -> None:
        req = open_request(
            tenant_id="t1",
            student_id="s1",
            event_code="ski-week",
            amount=Decimal("250.00"),
            currency="USD",
            guardian_threshold=Decimal("100.00"),
        )
        self.assertTrue(req.requires_guardian_approval)
        self.assertEqual(req.state, "awaiting_guardian")

    def test_pay_requires_guardian_when_above_threshold(self) -> None:
        req = open_request(
            tenant_id="t1",
            student_id="s1",
            event_code="ski",
            amount=Decimal("250.00"),
            currency="USD",
            guardian_threshold=Decimal("100.00"),
        )
        with self.assertRaises(PermissionToPayError):
            authorize_payment(req, tenant_id_raw_for_intent="t1")

    def test_full_happy_path_records_guardian_hash(self) -> None:
        req = open_request(
            tenant_id="t1",
            student_id="s1",
            event_code="ski",
            amount=Decimal("250.00"),
            currency="USD",
            guardian_threshold=Decimal("100.00"),
        )
        record_guardian_approval(
            req,
            guardian_id="guardian-9",
            approved_at_iso="2026-05-25T08:00:00Z",
            method="portal",
        )
        self.assertNotEqual(req.guardian_approval.guardian_id, "guardian-9")
        authorize_payment(req, tenant_id_raw_for_intent="t1")
        self.assertEqual(req.state, "paid")
        self.assertTrue(req.payment_result.success)
