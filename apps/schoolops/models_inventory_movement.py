"""Inventory movement ledger (metric 14).

Append-only by design: quantity history is an audit trail. Mutations go through
``record_inventory_movement`` which creates new rows; ORM update/delete is refused.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models

from apps.platform_runtime.append_only import AppendOnlyManager, AppendOnlyModelMixin


class InventoryMovement(AppendOnlyModelMixin, models.Model):
    class MovementType(models.TextChoices):
        CHECKOUT = "checkout", "Checkout"
        RETURN = "return", "Return"
        CONSUME = "consume", "Consume"
        TRANSFER = "transfer", "Transfer"
        LOSS = "loss", "Loss"
        ADJUST = "adjust", "Adjustment"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="inventory_movements",
    )
    item = models.ForeignKey(
        "schoolops.InventoryItem",
        on_delete=models.CASCADE,
        related_name="movements",
    )
    movement_type = models.CharField(
        max_length=16,
        choices=MovementType.choices,
        default=MovementType.ADJUST,
    )
    quantity_delta = models.IntegerField(
        help_text="Signed change applied to item.quantity.",
    )
    quantity_after = models.PositiveIntegerField()
    notes = models.CharField(max_length=500, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_movements_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyManager()

    class Meta:
        app_label = "schoolops"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "item", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.item_id} {self.movement_type} {self.quantity_delta:+d}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionDenied(
                "InventoryMovement records are append-only and cannot be updated."
            )
        return super().save(*args, **kwargs)
