"""Inventory movement ledger tests (metric 14)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.schoolops.inventory_services import InventoryMovementError, record_inventory_movement
from apps.schoolops.models import InventoryItem
from apps.schoolops.models_inventory_movement import InventoryMovement
from apps.schools.models import School

User = get_user_model()


class InventoryMovementTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Inventory Ledger School",
            slug="inventory-ledger-school",
            subdomain="inventory-ledger-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="inventory_ops",
            password="testpass123",
        )
        self.item = InventoryItem.objects.create(
            school=self.school,
            name="Science kits",
            quantity=10,
            location="Store A",
        )

    def test_adjustment_creates_ledger_row(self):
        movement = record_inventory_movement(
            school=self.school,
            item=self.item,
            movement_type=InventoryMovement.MovementType.ADJUST,
            quantity_delta=-2,
            recorded_by=self.user,
            notes="Damaged units",
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 8)
        self.assertEqual(movement.quantity_after, 8)
        self.assertEqual(movement.quantity_delta, -2)
        self.assertEqual(movement.notes, "Damaged units")

    def test_rejects_below_zero(self):
        with self.assertRaises(InventoryMovementError):
            record_inventory_movement(
                school=self.school,
                item=self.item,
                movement_type=InventoryMovement.MovementType.CONSUME,
                quantity_delta=-50,
            )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 10)

    def test_ledger_rows_are_append_only(self):
        from django.core.exceptions import PermissionDenied

        from apps.platform_runtime.append_only import AppendOnlyDeleteError

        movement = record_inventory_movement(
            school=self.school,
            item=self.item,
            movement_type=InventoryMovement.MovementType.ADJUST,
            quantity_delta=1,
            recorded_by=self.user,
        )
        movement.notes = "tamper"
        with self.assertRaises(PermissionDenied):
            movement.save()
        with self.assertRaises(AppendOnlyDeleteError):
            movement.delete()
        with self.assertRaises(AppendOnlyDeleteError):
            InventoryMovement.objects.filter(pk=movement.pk).delete()
        self.assertTrue(InventoryMovement.objects.filter(pk=movement.pk).exists())
