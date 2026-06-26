"""Inventory movement ledger services."""

from __future__ import annotations

from typing import Any

from django.db import transaction


class InventoryMovementError(Exception):
    pass


@transaction.atomic
def record_inventory_movement(
    *,
    school: Any,
    item: Any,
    movement_type: str,
    quantity_delta: int,
    recorded_by: Any | None = None,
    notes: str = "",
) -> Any:
    from apps.schoolops.models import InventoryItem
    from apps.schoolops.models_inventory_movement import InventoryMovement

    if quantity_delta == 0:
        raise InventoryMovementError("quantity_delta must be non-zero")
    locked = InventoryItem.objects.select_for_update().get(pk=item.pk, school=school)
    new_qty = int(locked.quantity) + int(quantity_delta)
    if new_qty < 0:
        raise InventoryMovementError("quantity would fall below zero")
    locked.quantity = new_qty
    locked.save(update_fields=["quantity"])
    return InventoryMovement.objects.create(
        school=school,
        item=locked,
        movement_type=movement_type,
        quantity_delta=int(quantity_delta),
        quantity_after=new_qty,
        notes=(notes or "")[:500],
        recorded_by=recorded_by,
    )
