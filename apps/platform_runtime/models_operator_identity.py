"""Platform operator profile, invites, and dual-control promotion requests."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.platform_runtime.operator_identity import TIER_CHOICES


class PlatformOperatorProfile(models.Model):
    class Status(models.TextChoices):
        INVITED = "invited", "Invited"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        OFFBOARDED = "offboarded", "Offboarded"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_operator_profile",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.INVITED,
        db_index=True,
    )
    tier = models.CharField(
        max_length=32,
        choices=TIER_CHOICES,
        default="support",
    )
    extra_scopes = models.JSONField(
        default=list,
        blank=True,
        help_text="Optional extra platform.* scope codes beyond tier defaults.",
    )
    mfa_required = models.BooleanField(default=True)
    break_glass_only = models.BooleanField(
        default=False,
        help_text="When true, operator should use break-glass admin sparingly.",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_operator_invites_sent",
    )
    invited_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    offboarded_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorprofile"
        verbose_name = "Platform operator profile"
        verbose_name_plural = "Platform operator profiles"

    def __str__(self) -> str:
        return f"{self.user_id} ({self.tier}/{self.status})"

    def mark_active(self):
        self.status = self.Status.ACTIVE
        self.activated_at = timezone.now()
        self.offboarded_at = None

    def mark_offboarded(self):
        self.status = self.Status.OFFBOARDED
        self.offboarded_at = timezone.now()


class PlatformOperatorInvite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    tier = models.CharField(max_length=32, choices=TIER_CHOICES, default="support")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_operator_invite_tokens",
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorinvite"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"invite:{self.email}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_pending(self) -> bool:
        return self.accepted_at is None and not self.is_expired


class PlatformOperatorPromotionRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending peer approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_promotion_requests",
    )
    requested_tier = models.CharField(max_length=32, choices=TIER_CHOICES)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="platform_promotions_requested",
    )
    peer_approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_promotions_approved",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorpromotionrequest"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"promotion:{self.target_user_id}->{self.requested_tier} ({self.status})"
