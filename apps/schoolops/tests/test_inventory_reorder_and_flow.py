"""Metric 14 — inventory checkout/transfer flow + reorder-alert producer tests."""

import uuid

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.finance.models import Notification
from apps.schoolops.inventory_services import (
    InventoryMovementError,
    checkout_inventory,
    consume_inventory,
    record_inventory_loss,
    record_inventory_movement,
    return_inventory,
    transfer_inventory,
)
from apps.schoolops.models import InventoryItem
from apps.schoolops.models_inventory_movement import InventoryMovement
from apps.schoolops.tasks import notify_low_inventory_stock, sweep_low_inventory_stock
from apps.schoolops.views_tenant_ops import ops_inventory
from apps.schools.models import School, SchoolMembership

User = get_user_model()


def _make_school():
    tag = uuid.uuid4().hex[:10]
    return School.objects.create(
        name=f"Inv {tag}",
        slug=f"inv-{tag}",
        subdomain=f"inv-{tag}",
        is_active=True,
        features={"inventory": True},
    )


def _make_admin(school):
    user = User.objects.create_user(
        username=f"adm-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@t.test",
        password="x",
        role=User.Role.ADMIN,
    )
    SchoolMembership.objects.create(user=user, school=school, role="ADMIN")
    return user


class InventoryCheckoutTransferTests(TestCase):
    def setUp(self):
        self.school = _make_school()
        self.user = _make_admin(self.school)
        self.item = InventoryItem.objects.create(
            school=self.school, name="Laptops", quantity=10, location="Store A",
        )

    def test_checkout_decrements_and_ledgers(self):
        checkout_inventory(
            school=self.school, item=self.item, quantity=3,
            recorded_by=self.user, checked_out_to="Coach Lee",
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 7)
        mv = InventoryMovement.objects.get(item=self.item)
        self.assertEqual(mv.movement_type, InventoryMovement.MovementType.CHECKOUT)
        self.assertEqual(mv.quantity_delta, -3)
        self.assertEqual(mv.quantity_after, 7)
        self.assertIn("Coach Lee", mv.notes)

    def test_checkout_with_student_creates_resource_return(self):
        from apps.academics.models import AcademicYear
        from apps.people.models import StudentProfile, StudentResourceReturn

        year = AcademicYear.objects.create(
            name="Y1",
            start_date="2025-01-01",
            end_date="2025-12-31",
            school=self.school,
            is_active=True,
        )
        student = StudentProfile.objects.create(
            first_name="Pat",
            last_name="Lee",
            date_of_birth="2012-01-01",
            student_code=f"S{uuid.uuid4().hex[:6]}",
            school=self.school,
            academic_year=year,
        )
        checkout_inventory(
            school=self.school,
            item=self.item,
            quantity=1,
            recorded_by=self.user,
            checked_out_to="Pat Lee",
            student=student,
            academic_year=year,
        )
        row = StudentResourceReturn.objects.get(
            student=student, academic_year=year, item_label="Laptops"
        )
        self.assertIsNone(row.returned_at)

    def test_checkout_insufficient_rejected(self):
        with self.assertRaises(InventoryMovementError):
            checkout_inventory(school=self.school, item=self.item, quantity=50)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 10)
        self.assertFalse(InventoryMovement.objects.filter(item=self.item).exists())

    def test_checkout_non_positive_rejected(self):
        with self.assertRaises(InventoryMovementError):
            checkout_inventory(school=self.school, item=self.item, quantity=0)

    def test_transfer_moves_between_items_total_conserved(self):
        dest = InventoryItem.objects.create(
            school=self.school, name="Laptops", quantity=2, location="Store B",
        )
        before_total = self.item.quantity + dest.quantity
        out_mv, in_mv = transfer_inventory(
            school=self.school, source_item=self.item, dest_item=dest,
            quantity=4, recorded_by=self.user,
        )
        self.item.refresh_from_db()
        dest.refresh_from_db()
        self.assertEqual(self.item.quantity, 6)
        self.assertEqual(dest.quantity, 6)
        self.assertEqual(self.item.quantity + dest.quantity, before_total)
        self.assertEqual(out_mv.movement_type, InventoryMovement.MovementType.TRANSFER)
        self.assertEqual(out_mv.quantity_delta, -4)
        self.assertEqual(in_mv.quantity_delta, 4)

    def test_transfer_insufficient_source_rolls_back(self):
        dest = InventoryItem.objects.create(
            school=self.school, name="Laptops", quantity=2, location="Store B",
        )
        with self.assertRaises(InventoryMovementError):
            transfer_inventory(
                school=self.school, source_item=self.item, dest_item=dest,
                quantity=99, recorded_by=self.user,
            )
        self.item.refresh_from_db()
        dest.refresh_from_db()
        # Nothing committed on either side.
        self.assertEqual(self.item.quantity, 10)
        self.assertEqual(dest.quantity, 2)
        self.assertEqual(InventoryMovement.objects.count(), 0)

    def test_transfer_to_self_rejected(self):
        with self.assertRaises(InventoryMovementError):
            transfer_inventory(
                school=self.school, source_item=self.item, dest_item=self.item,
                quantity=1,
            )

    # ---- view wiring (intent routing) -----------------------------------

    def _req(self, data):
        r = RequestFactory().post("/backend/ops/inventory/", data)
        r.user = self.user
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_checkout_intent_via_view(self):
        resp = ops_inventory(self._req({
            "intent": "checkout",
            "checkout_item_id": str(self.item.pk),
            "checkout_quantity": "2",
            "checked_out_to": "Lab 3",
        }))
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 8)
        self.assertTrue(
            InventoryMovement.objects.filter(
                item=self.item,
                movement_type=InventoryMovement.MovementType.CHECKOUT,
            ).exists()
        )

    def test_transfer_intent_via_view(self):
        dest = InventoryItem.objects.create(
            school=self.school, name="Laptops", quantity=1, location="Store B",
        )
        resp = ops_inventory(self._req({
            "intent": "transfer",
            "transfer_source_id": str(self.item.pk),
            "transfer_dest_id": str(dest.pk),
            "transfer_quantity": "5",
        }))
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        dest.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)
        self.assertEqual(dest.quantity, 6)

    # ---- return / consume / loss producers ------------------------------

    def test_return_increments_and_ledgers(self):
        return_inventory(
            school=self.school, item=self.item, quantity=4,
            recorded_by=self.user, returned_from="Coach Lee",
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 14)
        mv = InventoryMovement.objects.get(item=self.item)
        self.assertEqual(mv.movement_type, InventoryMovement.MovementType.RETURN)
        self.assertEqual(mv.quantity_delta, 4)
        self.assertEqual(mv.quantity_after, 14)
        self.assertIn("Coach Lee", mv.notes)

    def test_consume_decrements_and_ledgers(self):
        consume_inventory(
            school=self.school, item=self.item, quantity=3, recorded_by=self.user,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 7)
        mv = InventoryMovement.objects.get(item=self.item)
        self.assertEqual(mv.movement_type, InventoryMovement.MovementType.CONSUME)
        self.assertEqual(mv.quantity_delta, -3)

    def test_consume_insufficient_rejected(self):
        with self.assertRaises(InventoryMovementError):
            consume_inventory(school=self.school, item=self.item, quantity=99)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 10)
        self.assertFalse(InventoryMovement.objects.filter(item=self.item).exists())

    def test_loss_decrements_and_ledgers(self):
        record_inventory_loss(
            school=self.school, item=self.item, quantity=2,
            recorded_by=self.user, reason="Water damage",
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 8)
        mv = InventoryMovement.objects.get(item=self.item)
        self.assertEqual(mv.movement_type, InventoryMovement.MovementType.LOSS)
        self.assertEqual(mv.quantity_delta, -2)
        self.assertIn("Water damage", mv.notes)

    def test_loss_insufficient_rejected(self):
        with self.assertRaises(InventoryMovementError):
            record_inventory_loss(school=self.school, item=self.item, quantity=99)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 10)

    # ---- view wiring for the stock_event intent -------------------------

    def test_return_intent_via_view(self):
        resp = ops_inventory(self._req({
            "intent": "stock_event", "movement": "return",
            "stock_item_id": str(self.item.pk), "stock_quantity": "5",
        }))
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 15)
        self.assertTrue(InventoryMovement.objects.filter(
            item=self.item, movement_type=InventoryMovement.MovementType.RETURN,
        ).exists())

    def test_consume_intent_via_view(self):
        resp = ops_inventory(self._req({
            "intent": "stock_event", "movement": "consume",
            "stock_item_id": str(self.item.pk), "stock_quantity": "4",
        }))
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 6)
        self.assertTrue(InventoryMovement.objects.filter(
            item=self.item, movement_type=InventoryMovement.MovementType.CONSUME,
        ).exists())

    def test_loss_intent_via_view(self):
        resp = ops_inventory(self._req({
            "intent": "stock_event", "movement": "loss",
            "stock_item_id": str(self.item.pk), "stock_quantity": "1",
            "stock_reason": "Water damage",
        }))
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 9)
        row = InventoryMovement.objects.filter(
            item=self.item, movement_type=InventoryMovement.MovementType.LOSS,
        ).first()
        self.assertIsNotNone(row)
        self.assertIn("Water damage", row.notes)

    def test_loss_via_view_requires_reason_or_notes(self):
        ops_inventory(self._req({
            "intent": "stock_event", "movement": "loss",
            "stock_item_id": str(self.item.pk), "stock_quantity": "1",
        }))
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 10)
        self.assertFalse(InventoryMovement.objects.filter(item=self.item).exists())

    def test_consume_exact_stock_to_zero(self):
        consume_inventory(school=self.school, item=self.item, quantity=10)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 0)

    def test_consume_notes_round_trip_via_view(self):
        resp = ops_inventory(self._req({
            "intent": "stock_event", "movement": "consume",
            "stock_item_id": str(self.item.pk), "stock_quantity": "2",
            "stock_notes": "Science lab week",
        }))
        self.assertEqual(resp.status_code, 302)
        row = InventoryMovement.objects.filter(
            item=self.item, movement_type=InventoryMovement.MovementType.CONSUME,
        ).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.notes, "Science lab week")

    def test_stock_event_invalid_movement_creates_nothing(self):
        # An unknown movement value must not touch stock or write a ledger row.
        ops_inventory(self._req({
            "intent": "stock_event", "movement": "teleport",
            "stock_item_id": str(self.item.pk), "stock_quantity": "3",
        }))
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 10)
        self.assertFalse(InventoryMovement.objects.filter(item=self.item).exists())


class InventoryReorderAlertTests(TestCase):
    def setUp(self):
        self.school = _make_school()
        self.admin = _make_admin(self.school)

    def _alerts_for(self, user):
        return Notification.objects.filter(recipient=user)

    def test_is_low_property(self):
        item = InventoryItem(quantity=5, reorder_threshold=0)
        self.assertFalse(item.is_low)  # threshold 0 disables
        item = InventoryItem(quantity=5, reorder_threshold=5)
        self.assertTrue(item.is_low)  # at threshold
        item = InventoryItem(quantity=6, reorder_threshold=5)
        self.assertFalse(item.is_low)  # above threshold

    def test_alert_fires_once_on_crossing(self):
        item = InventoryItem.objects.create(
            school=self.school, name="Markers", quantity=10, reorder_threshold=5,
        )
        # Not low at creation → no alert yet.
        self.assertEqual(self._alerts_for(self.admin).count(), 0)
        record_inventory_movement(
            school=self.school, item=item,
            movement_type=InventoryMovement.MovementType.CONSUME,
            quantity_delta=-6,  # 10 -> 4, crosses <= 5
        )
        item.refresh_from_db()
        self.assertTrue(item.is_low)
        self.assertIsNotNone(item.last_low_stock_notified_at)
        self.assertEqual(item.low_stock_notification_count, 1)
        self.assertEqual(self._alerts_for(self.admin).count(), 1)

    def test_alert_idempotent_while_low(self):
        item = InventoryItem.objects.create(
            school=self.school, name="Markers", quantity=10, reorder_threshold=5,
        )
        record_inventory_movement(
            school=self.school, item=item,
            movement_type=InventoryMovement.MovementType.CONSUME, quantity_delta=-6,
        )
        # Another downward move while still low — must NOT re-fire the episode.
        record_inventory_movement(
            school=self.school, item=item,
            movement_type=InventoryMovement.MovementType.CONSUME, quantity_delta=-1,
        )
        # A direct task re-run is also a no-op while the episode is open.
        notify_low_inventory_stock(inventory_item_id=item.pk)
        item.refresh_from_db()
        self.assertEqual(item.low_stock_notification_count, 1)
        self.assertEqual(self._alerts_for(self.admin).count(), 1)

    def test_restock_resets_episode_then_refires(self):
        item = InventoryItem.objects.create(
            school=self.school, name="Markers", quantity=10, reorder_threshold=5,
        )
        record_inventory_movement(
            school=self.school, item=item,
            movement_type=InventoryMovement.MovementType.CONSUME, quantity_delta=-6,
        )
        item.refresh_from_db()
        self.assertEqual(item.low_stock_notification_count, 1)
        # Restock above the reorder level — episode closes.
        record_inventory_movement(
            school=self.school, item=item,
            movement_type=InventoryMovement.MovementType.RETURN, quantity_delta=+10,
        )
        item.refresh_from_db()
        self.assertFalse(item.is_low)
        self.assertIsNone(item.last_low_stock_notified_at)
        self.assertEqual(item.low_stock_notification_count, 0)
        # Dip again — a fresh episode re-fires.
        record_inventory_movement(
            school=self.school, item=item,
            movement_type=InventoryMovement.MovementType.CONSUME, quantity_delta=-12,
        )
        item.refresh_from_db()
        self.assertTrue(item.is_low)
        self.assertIsNotNone(item.last_low_stock_notified_at)
        self.assertEqual(item.low_stock_notification_count, 1)

    def test_alert_recipients_are_school_scoped(self):
        other_school = _make_school()
        other_admin = _make_admin(other_school)
        item = InventoryItem.objects.create(
            school=self.school, name="Markers", quantity=10, reorder_threshold=5,
        )
        record_inventory_movement(
            school=self.school, item=item,
            movement_type=InventoryMovement.MovementType.CONSUME, quantity_delta=-6,
        )
        self.assertEqual(self._alerts_for(self.admin).count(), 1)
        self.assertEqual(self._alerts_for(other_admin).count(), 0)

    def test_sweep_alerts_low_rows_the_signal_missed(self):
        item = InventoryItem.objects.create(
            school=self.school, name="Markers", quantity=10, reorder_threshold=5,
        )
        # Drop below threshold WITHOUT firing the signal (queryset update).
        InventoryItem.objects.filter(pk=item.pk).update(quantity=2)
        item.refresh_from_db()
        self.assertTrue(item.is_low)
        self.assertIsNone(item.last_low_stock_notified_at)

        summary = sweep_low_inventory_stock()
        self.assertGreaterEqual(summary["enqueued"], 1)
        item.refresh_from_db()
        self.assertIsNotNone(item.last_low_stock_notified_at)
        self.assertEqual(self._alerts_for(self.admin).count(), 1)
