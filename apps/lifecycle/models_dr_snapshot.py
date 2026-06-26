"""Immutable daily tenant DR snapshot metadata (signed, dual-store paths)."""

from __future__ import annotations

import uuid

from django.db import models


class TenantImmutableSnapshot(models.Model):
    """One row per school per UTC snapshot day."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="immutable_snapshots",
    )
    snapshot_date = models.DateField(db_index=True)
    primary_uri = models.CharField(max_length=512)
    secondary_uri = models.CharField(max_length=512, blank=True, default="")
    payload_sha256 = models.CharField(max_length=64)
    signature_hex = models.CharField(max_length=128)
    byte_size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-snapshot_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "snapshot_date"],
                name="uniq_tenant_immutable_snapshot_day",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.school_id} {self.snapshot_date} ({self.byte_size}B)"
