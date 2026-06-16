"""Platform operator profile, invites, and dual-control promotion requests."""

from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.platform_runtime.operator_identity import TIER_CHOICES

logger = logging.getLogger(__name__)


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


class OperatorTenantAssignment(models.Model):
    """Scopes which platform operators may impersonate / access which tenants.

    The platform.impersonate scope says an operator *may impersonate*; this
    model says *which tenants*. Hard-enforced in
    ``apps.schools.super_views_impersonation.switch_to_tenant``: a non-superuser
    operator must hold an active (unrevoked, unexpired) assignment for the
    target school — or an active JIT grant — before switch-to-tenant is
    permitted; otherwise 403. Superusers are the platform root of trust and
    bypass the check (so the owner can never self-lock before any assignment
    exists). Lives in the public schema (platform_runtime is SHARED_APPS) so the
    operator console can read it.
    """

    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="operator_tenant_assignments",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="operator_assignments",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operator_tenant_grants",
    )
    reason = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional time-box; null = no expiry (still revocable).",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operator_tenant_revocations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatortenantassignment"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["operator", "school"]),
            models.Index(fields=["school"]),
        ]

    def __str__(self) -> str:
        return f"assign:{self.operator_id}->{self.school_id}"

    def is_active(self, *, now=None) -> bool:
        now = now or timezone.now()
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= now:
            return False
        return True

    @classmethod
    def has_active(cls, operator, school, *, now=None) -> bool:
        """True when ``operator`` holds a live assignment for ``school``."""
        operator_pk = getattr(operator, "pk", None)
        school_pk = getattr(school, "pk", None)
        if operator_pk is None or school_pk is None:
            return False
        now = now or timezone.now()
        return (
            cls.objects.filter(
                operator_id=operator_pk,
                school_id=school_pk,
                revoked_at__isnull=True,
            )
            .filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))
            .exists()
        )

    def record_lifecycle_audit(
        self, *, actor, action, reason, ip=None, user_agent=""
    ) -> None:
        """Append an AuditLog row for a grant / revoke / delete on this row.

        Reusable from the Django admin AND any future programmatic grant path,
        so the assignment lifecycle (who granted/revoked which operator on which
        tenant, and why) is always captured in the same shape. Best-effort: an
        audit-write failure is logged but never propagated into the caller — the
        grant/revoke must not break because the audit DB hiccuped.
        """
        try:
            from apps.compliance.models_audit import AuditLog

            AuditLog.objects.create(
                user=actor if getattr(actor, "pk", None) else None,
                ip_address=ip,
                user_agent=(user_agent or "")[:500],
                action=action,
                model_name="OperatorTenantAssignment",
                object_id=str(self.pk or ""),
                object_repr=str(self)[:500],
                app_label="platform_runtime",
                sensitivity=AuditLog.Sensitivity.HIGH,
                new_values={
                    "operator_id": self.operator_id,
                    "school_id": str(self.school_id),
                    "granted_by_id": self.granted_by_id,
                    "expires_at": (
                        self.expires_at.isoformat() if self.expires_at else None
                    ),
                    "revoked": self.revoked_at is not None,
                },
                reason=str(reason)[:255],
            )
        except Exception:  # noqa: BLE001 — audit is best-effort, never breaks the grant
            logger.warning(
                "OperatorTenantAssignment lifecycle audit failed", exc_info=True
            )
