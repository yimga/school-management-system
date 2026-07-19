"""Inventory movement ledger services."""

from __future__ import annotations

from typing import Any

from django.db import transaction


class InventoryMovementError(Exception):
    pass


# Sane per-movement quantity ceiling (mirrors the ops item-quantity cap in
# views_tenant_ops.ops_inventory) so a fat-fingered checkout/transfer can't
# create an absurd ledger row.
_MAX_MOVEMENT_QTY = 10_000_000  # magic-number-allow: per-movement quantity ceiling


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


def _coerce_positive_qty(quantity: Any, *, label: str) -> int:
    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        raise InventoryMovementError(f"{label} quantity must be a whole number")
    if qty <= 0:
        raise InventoryMovementError(f"{label} quantity must be positive")
    if qty > _MAX_MOVEMENT_QTY:
        raise InventoryMovementError(f"{label} quantity is too large")
    return qty


def checkout_inventory(
    *,
    school: Any,
    item: Any,
    quantity: Any,
    recorded_by: Any | None = None,
    checked_out_to: str = "",
    notes: str = "",
    student: Any | None = None,
    academic_year: Any | None = None,
) -> Any:
    """Check ``quantity`` units of ``item`` out to a person.

    Records a single CHECKOUT movement with a negative delta. Insufficient
    stock is rejected by :func:`record_inventory_movement` (quantity-below-zero
    guard), which raises :class:`InventoryMovementError`.

    When ``student`` is provided (family-facing path), also upserts an
    outstanding ``StudentResourceReturn`` so parents can see issued items.
    """
    from apps.schoolops.models_inventory_movement import InventoryMovement

    qty = _coerce_positive_qty(quantity, label="Checkout")
    who = (checked_out_to or "").strip()
    note = (notes or "").strip() or (
        f"Checked out to {who}" if who else "Checkout"
    )
    movement = record_inventory_movement(
        school=school,
        item=item,
        movement_type=InventoryMovement.MovementType.CHECKOUT,
        quantity_delta=-qty,
        recorded_by=recorded_by,
        notes=note,
    )
    if student is not None:
        year = academic_year or getattr(student, "academic_year", None)
        if year is not None and getattr(student, "school_id", None) == getattr(
            school, "pk", None
        ):
            from apps.people.models import StudentResourceReturn

            label = (getattr(item, "name", None) or who or "Issued item")[:120]
            StudentResourceReturn.objects.get_or_create(
                student=student,
                academic_year=year,
                item_label=label,
                defaults={"notes": note[:500]},
            )
    return movement


def transfer_inventory(
    *,
    school: Any,
    source_item: Any,
    dest_item: Any,
    quantity: Any,
    recorded_by: Any | None = None,
    notes: str = "",
) -> tuple:
    """Move ``quantity`` units from ``source_item`` to ``dest_item`` atomically.

    Writes two TRANSFER ledger rows (``-qty`` out of the source, ``+qty`` into
    the destination) inside a single transaction, so total stock across the two
    items is conserved and an insufficient-stock source rolls the whole transfer
    back (nothing is committed). Returns ``(out_movement, in_movement)``.
    """
    from apps.schoolops.models_inventory_movement import InventoryMovement

    qty = _coerce_positive_qty(quantity, label="Transfer")
    if getattr(source_item, "pk", None) == getattr(dest_item, "pk", None):
        raise InventoryMovementError("cannot transfer an item to itself")

    src_loc = (getattr(source_item, "location", "") or "").strip() or "—"
    dst_loc = (getattr(dest_item, "location", "") or "").strip() or "—"
    base_note = (notes or "").strip() or f"Transfer {src_loc} → {dst_loc}"

    with transaction.atomic():
        out_movement = record_inventory_movement(
            school=school,
            item=source_item,
            movement_type=InventoryMovement.MovementType.TRANSFER,
            quantity_delta=-qty,
            recorded_by=recorded_by,
            notes=f"{base_note} (out)",
        )
        in_movement = record_inventory_movement(
            school=school,
            item=dest_item,
            movement_type=InventoryMovement.MovementType.TRANSFER,
            quantity_delta=qty,
            recorded_by=recorded_by,
            notes=f"{base_note} (in)",
        )
    return out_movement, in_movement


def return_inventory(
    *,
    school: Any,
    item: Any,
    quantity: Any,
    recorded_by: Any | None = None,
    returned_from: str = "",
    notes: str = "",
) -> Any:
    """Return checked-out units back into stock.

    Records a single RETURN movement with a POSITIVE delta (the inverse of a
    checkout), so stock goes back up and a restock can close a low-stock episode.
    """
    from apps.schoolops.models_inventory_movement import InventoryMovement

    qty = _coerce_positive_qty(quantity, label="Return")
    who = (returned_from or "").strip()
    note = (notes or "").strip() or (f"Returned by {who}" if who else "Return")
    return record_inventory_movement(
        school=school,
        item=item,
        movement_type=InventoryMovement.MovementType.RETURN,
        quantity_delta=qty,
        recorded_by=recorded_by,
        notes=note,
    )


def consume_inventory(
    *,
    school: Any,
    item: Any,
    quantity: Any,
    recorded_by: Any | None = None,
    notes: str = "",
) -> Any:
    """Consume (use up) units — a negative CONSUME movement.

    Consumption cannot exceed stock: the quantity-below-zero guard in
    :func:`record_inventory_movement` rejects over-consumption.
    """
    from apps.schoolops.models_inventory_movement import InventoryMovement

    qty = _coerce_positive_qty(quantity, label="Consume")
    note = (notes or "").strip() or "Consumed"
    return record_inventory_movement(
        school=school,
        item=item,
        movement_type=InventoryMovement.MovementType.CONSUME,
        quantity_delta=-qty,
        recorded_by=recorded_by,
        notes=note,
    )


def record_inventory_loss(
    *,
    school: Any,
    item: Any,
    quantity: Any,
    recorded_by: Any | None = None,
    reason: str = "",
    notes: str = "",
) -> Any:
    """Record lost/damaged/stolen units — a negative LOSS movement.

    Same below-zero guard as consumption: you cannot lose more than you hold.
    """
    from apps.schoolops.models_inventory_movement import InventoryMovement

    qty = _coerce_positive_qty(quantity, label="Loss")
    why = (reason or "").strip()
    note = (notes or "").strip() or (f"Loss: {why}" if why else "Loss")
    return record_inventory_movement(
        school=school,
        item=item,
        movement_type=InventoryMovement.MovementType.LOSS,
        quantity_delta=-qty,
        recorded_by=recorded_by,
        notes=note,
    )
