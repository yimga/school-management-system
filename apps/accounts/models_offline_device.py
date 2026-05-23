"""Offline device registration + capability tokens (SODP batch 1408)."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class DeviceRegistration(models.Model):
    """Registered client device for offline capability minting."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_registrations",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="device_registrations",
    )
    device_id = models.CharField(max_length=128, db_index=True)
    public_key_fingerprint = models.CharField(max_length=64, blank=True, default="")
    permission_bitmap = models.JSONField(default=list, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "accounts"
        db_table = "accounts_device_registration"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "user", "device_id"],
                name="uniq_device_per_user_school",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "revoked_at"]),
        ]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def touch_seen(self) -> None:
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at"])


class OfflineCapabilityToken(models.Model):
    """Short-lived offline authorization blob (minted online only)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(
        DeviceRegistration,
        on_delete=models.CASCADE,
        related_name="capability_tokens",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="offline_capability_tokens",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="offline_capability_tokens",
    )
    token_fingerprint = models.CharField(max_length=64, db_index=True)
    permission_bitmap = models.JSONField(default=list, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "accounts"
        db_table = "accounts_offline_capability_token"
        indexes = [
            models.Index(fields=["school", "expires_at"]),
        ]

    @property
    def is_valid(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at > timezone.now()


__all__ = ["DeviceRegistration", "OfflineCapabilityToken"]
