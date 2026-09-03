"""M14 -- inventory movement-ledger conservation and the reorder threshold edge.

On-hand is a STORED column (``InventoryItem.quantity``) and the movement ledger
is a parallel append-only trail carrying a signed ``quantity_delta`` and a
denormalised ``quantity_after`` snapshot. Nothing anywhere reconciles the two.
The existing suite is strong on flow and on the alert episode state machine, but
across ~23 tests only one line touches conservation -- a single
``item.quantity + dest.quantity == before_total`` inside the transfer test --
and nothing ever checks that ``quantity_after`` forms a consistent chain.

That is the thing that actually rots. ``quantity_after`` is written once at
insert time and never revisited, so a producer that updates ``quantity`` without
going through ``record_inventory_movement`` (the codebase does exactly this in
places, e.g. a bare ``.update(quantity=N)``) leaves the ledger telling a
different story from the stock count, permanently and silently.

This module asserts conservation as an invariant over a long mixed sequence
through the real producers, and pins the reorder alert at its exact boundary by
observing real ``Notification`` rows rather than a property on an unsaved
instance.
"""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.test import TestCase

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
from apps.schools.models import School, SchoolMembership

User = get_user_model()


def _make_school():
    tag = uuid.uuid4().hex[:10]
    return School.objects.create(
        name=f"M14 {tag}",
        slug=f"m14-{tag}",
        subdomain=f"m14-{tag}",
        is_active=True,
        features={"inventory": True},
    )


def _make_admin(school):
    user = User.objects.create_user(
        username=f"m14-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@m14.test",
        password="x",
        role=User.Role.ADMIN,
    )
    SchoolMembership.objects.create(user=user, school=school, role="ADMIN")
    return user


class LedgerConservationTests(TestCase):
    """on-hand == opening stock + every signed delta, always."""

    OPENING = 100

    def setUp(self):
        self.school = _make_school()
        self.user = _make_admin(self.school)
        self.item = InventoryItem.objects.create(
            school=self.school,
            name="Tablets",
            quantity=self.OPENING,
            location="Store A",
        )

    def _ledger_sum(self, item=None) -> int:
        item = item or self.item
        return int(
            InventoryMovement.objects.filter(item=item).aggregate(
                total=Sum("quantity_delta")
            )["total"]
            or 0
        )

    def _assert_conserved(self, item=None, *, opening=None):
        item = item or self.item
        opening = self.OPENING if opening is None else opening
        item.refresh_from_db()
        self.assertEqual(
            item.quantity,
            opening + self._ledger_sum(item),
            msg=(
                f"stock {item.quantity} != opening {opening} + ledger "
                f"{self._ledger_sum(item)} -- the ledger and the stock count "
                "have diverged"
            ),
        )

    def test_a_long_mixed_sequence_conserves(self):
        """Every producer in the module, interleaved, on one item."""
        checkout_inventory(
            school=self.school, item=self.item, quantity=7, recorded_by=self.user
        )
        consume_inventory(
            school=self.school, item=self.item, quantity=13, recorded_by=self.user
        )
        return_inventory(
            school=self.school, item=self.item, quantity=4, recorded_by=self.user
        )
        record_inventory_loss(
            school=self.school, item=self.item, quantity=2, recorded_by=self.user
        )
        record_inventory_movement(
            school=self.school,
            item=self.item,
            movement_type=InventoryMovement.MovementType.ADJUST,
            quantity_delta=+25,
            recorded_by=self.user,
        )
        consume_inventory(
            school=self.school, item=self.item, quantity=1, recorded_by=self.user
        )

        # The fixture really did move stock -- a conserved no-op proves nothing.
        self.assertEqual(InventoryMovement.objects.filter(item=self.item).count(), 6)
        self.assertEqual(self._ledger_sum(), -7 - 13 + 4 - 2 + 25 - 1)
        self._assert_conserved()
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 106)

    def test_quantity_after_forms_a_consistent_chain(self):
        """Each snapshot must equal the running balance at that point.

        ``quantity_after`` is what the audit trail shows an auditor. If it does
        not chain, the trail is decorative.
        """
        for delta in (-5, -5, +12, -30, +3, -1, -4, +20):
            record_inventory_movement(
                school=self.school,
                item=self.item,
                movement_type=(
                    InventoryMovement.MovementType.ADJUST
                    if delta > 0
                    else InventoryMovement.MovementType.CONSUME
                ),
                quantity_delta=delta,
                recorded_by=self.user,
            )

        rows = list(
            InventoryMovement.objects.filter(item=self.item).order_by("id")
        )
        self.assertEqual(len(rows), 8)

        running = self.OPENING
        for index, row in enumerate(rows):
            running += row.quantity_delta
            self.assertEqual(
                row.quantity_after,
                running,
                msg=(
                    f"movement #{index} snapshot {row.quantity_after} != running "
                    f"balance {running}"
                ),
            )

        # The last snapshot is the live stock count.
        self.item.refresh_from_db()
        self.assertEqual(rows[-1].quantity_after, self.item.quantity)
        self._assert_conserved()

    def test_a_refused_movement_writes_nothing_at_all(self):
        """Below-zero refusal must leave BOTH sides untouched, or the refusal
        itself becomes the drift."""
        before_rows = InventoryMovement.objects.filter(item=self.item).count()
        with self.assertRaises(InventoryMovementError):
            consume_inventory(
                school=self.school,
                item=self.item,
                quantity=self.OPENING + 1,
                recorded_by=self.user,
            )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, self.OPENING)
        self.assertEqual(
            InventoryMovement.objects.filter(item=self.item).count(), before_rows
        )
        self._assert_conserved()

    def test_stock_may_be_driven_to_exactly_zero_but_not_past_it(self):
        consume_inventory(
            school=self.school,
            item=self.item,
            quantity=self.OPENING,
            recorded_by=self.user,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 0)
        self._assert_conserved()

        with self.assertRaises(InventoryMovementError):
            consume_inventory(
                school=self.school, item=self.item, quantity=1, recorded_by=self.user
            )
        self._assert_conserved()

    def test_transfer_conserves_the_LEDGER_across_both_items(self):
        """Existing coverage asserts the two stock counts balance. It never
        asserted the two ledgers do -- a transfer that wrote one leg would pass."""
        destination = InventoryItem.objects.create(
            school=self.school, name="Tablets (Annex)", quantity=10, location="Store B"
        )
        transfer_inventory(
            school=self.school,
            source_item=self.item,
            dest_item=destination,
            quantity=30,
            recorded_by=self.user,
        )

        self.assertEqual(self._ledger_sum(self.item), -30)
        self.assertEqual(self._ledger_sum(destination), +30)
        # Net zero across the pair: a transfer creates and destroys nothing.
        self.assertEqual(
            self._ledger_sum(self.item) + self._ledger_sum(destination), 0
        )
        self._assert_conserved(self.item, opening=self.OPENING)
        self._assert_conserved(destination, opening=10)

        self.item.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(self.item.quantity, 70)
        self.assertEqual(destination.quantity, 40)
        self.assertEqual(self.item.quantity + destination.quantity, self.OPENING + 10)

    def test_a_rolled_back_transfer_leaves_both_ledgers_empty(self):
        destination = InventoryItem.objects.create(
            school=self.school, name="Tablets (Annex)", quantity=10, location="Store B"
        )
        with self.assertRaises(InventoryMovementError):
            transfer_inventory(
                school=self.school,
                source_item=self.item,
                dest_item=destination,
                quantity=self.OPENING + 50,
                recorded_by=self.user,
            )
        self.assertEqual(self._ledger_sum(self.item), 0)
        self.assertEqual(self._ledger_sum(destination), 0)
        self._assert_conserved(self.item, opening=self.OPENING)
        self._assert_conserved(destination, opening=10)


class ReorderThresholdBoundaryTests(TestCase):
    """The alert edge, observed as real Notification rows.

    The suite's only boundary coverage builds UNSAVED ``InventoryItem(...)``
    objects and reads the ``is_low`` property. That pins the arithmetic but not
    the alert: the property could stay correct while the signal chain that turns
    it into a notification never fires. These drive real stock through the real
    producer and count real rows.
    """

    THRESHOLD = 5

    def setUp(self):
        self.school = _make_school()
        self.admin = _make_admin(self.school)

    def _item(self, quantity):
        return InventoryItem.objects.create(
            school=self.school,
            name="Markers",
            quantity=quantity,
            reorder_threshold=self.THRESHOLD,
        )

    def _alerts(self):
        return Notification.objects.filter(recipient=self.admin)

    def test_one_above_the_threshold_does_not_alert(self):
        item = self._item(10)
        consume_inventory(
            school=self.school, item=item, quantity=4, recorded_by=self.admin
        )  # 10 -> 6
        item.refresh_from_db()
        self.assertEqual(item.quantity, self.THRESHOLD + 1)
        self.assertFalse(item.is_low)
        self.assertEqual(self._alerts().count(), 0)
        self.assertIsNone(item.last_low_stock_notified_at)

    def test_exactly_at_the_threshold_alerts(self):
        """``<=``, not ``<``. One-off here means a school reorders a day late,
        every time."""
        item = self._item(10)
        consume_inventory(
            school=self.school, item=item, quantity=5, recorded_by=self.admin
        )  # 10 -> 5
        item.refresh_from_db()
        self.assertEqual(item.quantity, self.THRESHOLD)
        self.assertTrue(item.is_low)
        self.assertEqual(
            self._alerts().count(),
            1,
            msg="stock at exactly the reorder level did not raise an alert",
        )
        self.assertIsNotNone(item.last_low_stock_notified_at)
        self.assertEqual(item.low_stock_notification_count, 1)

    def test_the_alert_names_the_item(self):
        item = self._item(self.THRESHOLD + 1)
        consume_inventory(
            school=self.school, item=item, quantity=1, recorded_by=self.admin
        )
        alert = self._alerts().first()
        self.assertIsNotNone(alert)
        self.assertIn("Markers", alert.title)
        self.assertEqual(alert.school_id, self.school.id)

    def test_a_zero_threshold_disables_the_alert_entirely(self):
        item = InventoryItem.objects.create(
            school=self.school, name="Chalk", quantity=4, reorder_threshold=0
        )
        consume_inventory(
            school=self.school, item=item, quantity=4, recorded_by=self.admin
        )  # 4 -> 0, but no reorder level configured
        item.refresh_from_db()
        self.assertEqual(item.quantity, 0)
        self.assertFalse(item.is_low)
        self.assertEqual(self._alerts().count(), 0)

    def test_zero_stock_below_a_configured_threshold_alerts(self):
        """Guards the zero above: with a threshold set, empty stock DOES alert,
        so the previous test's zero is about the threshold, not about zero
        stock being unreachable."""
        item = self._item(3)
        consume_inventory(
            school=self.school, item=item, quantity=3, recorded_by=self.admin
        )
        item.refresh_from_db()
        self.assertEqual(item.quantity, 0)
        self.assertTrue(item.is_low)
        self.assertEqual(self._alerts().count(), 1)
