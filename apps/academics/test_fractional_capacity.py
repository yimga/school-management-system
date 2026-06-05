"""Phase 4E fractional capacity kernel tests."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.academics.fractional_capacity import (
    cross_campus_allocation_ok,
    effective_room_capacity,
)


class FractionalCapacityTests(SimpleTestCase):
    def test_effective_room_capacity_uses_fraction_attribute(self):
        room = SimpleNamespace(capacity=40, capacity_fraction="0.5")
        self.assertEqual(effective_room_capacity(room), Decimal("20.00"))

    def test_effective_room_capacity_clamps_fraction_above_one(self):
        room = SimpleNamespace(capacity=10, capacity_fraction="1.5")
        self.assertEqual(effective_room_capacity(room), Decimal("10.00"))

    def test_cross_campus_allocation_ok_within_budget(self):
        self.assertTrue(
            cross_campus_allocation_ok(
                existing_fraction=Decimal("0.4"),
                requested_fraction=Decimal("0.5"),
            )
        )
        self.assertFalse(
            cross_campus_allocation_ok(
                existing_fraction=Decimal("0.6"),
                requested_fraction=Decimal("0.5"),
            )
        )
