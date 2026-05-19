"""Multi-tenant social media integration models."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.accounts.legacy_hashes.encryption import encrypt_charfield

User = settings.AUTH_USER_MODEL


class SocialProvider(models.TextChoices):
    X = "x", "X (Twitter)"
    INSTAGRAM = "instagram", "Instagram"
    LINKEDIN = "linkedin", "LinkedIn"
    FACEBOOK = "facebook", "Facebook"


class SocialMediaIntegration(models.Model):
    """
    OAuth-connected social account.

    ``school`` NULL → platform manager (Tier 1) corporate feed.
    ``school`` set → tenant-scoped (Tier 2) campus feed.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="social_integrations",
        help_text="Null for platform-wide corporate integrations.",
    )
    provider = models.CharField(max_length=32, choices=SocialProvider.choices)
    handle = models.CharField(max_length=120, blank=True, default="")
    encrypted_oauth_token = encrypt_charfield(
        max_length=2048,
        blank=True,
        default="",
        help_text="Fernet-encrypted access token at rest.",
    )
    refresh_token = encrypt_charfield(
        max_length=2048,
        blank=True,
        default="",
    )
    token_expires_at = models.DateTimeField(null=True, blank=True)
    feed_cache_json = models.JSONField(default=list, blank=True)
    feed_cached_at = models.DateTimeField(null=True, blank=True)
    allowed_features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Subscription-tier feature flags, e.g. publish, emergency, analytics.",
    )
    webhook_secret = encrypt_charfield(max_length=512, blank=True, default="")
    audit_log = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    needs_reauth = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "provider"],
                condition=models.Q(is_active=True, school__isnull=False),
                name="uniq_active_social_provider_per_school",
            ),
            models.UniqueConstraint(
                fields=["provider"],
                condition=models.Q(is_active=True, school__isnull=True),
                name="uniq_active_platform_social_provider",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "provider"],
                name="social_medi_school__a0ea0d_idx",
            ),
            models.Index(
                fields=["school", "is_active"],
                name="social_medi_school__b8e2c1_idx",
            ),
        ]

    def __str__(self) -> str:
        scope = self.school.slug if self.school_id else "platform"
        return f"{scope}:{self.provider}"

    def append_audit(self, *, actor_id: str, action: str, detail: dict | None = None) -> None:
        entries = list(self.audit_log or [])
        entries.append(
            {
                "at": timezone.now().isoformat(),
                "actor_id": str(actor_id),
                "action": action,
                "detail": detail or {},
            }
        )
        self.audit_log = entries[-200:]
        self.save(update_fields=["audit_log", "updated_at"])

    def token_expired(self) -> bool:
        if not self.token_expires_at:
            return False
        return timezone.now() >= self.token_expires_at


class SocialPostPriority(models.IntegerChoices):
    STANDARD = 10, "Standard"
    EMERGENCY = 0, "Emergency"


class SocialPostOutbox(models.Model):
    """Outbound cross-post queue with tenant-scoped priority."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="social_post_outbox",
    )
    integration = models.ForeignKey(
        SocialMediaIntegration,
        on_delete=models.CASCADE,
        related_name="outbox_posts",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="social_posts_created",
    )
    body = models.TextField()
    media_urls = models.JSONField(default=list, blank=True)
    priority = models.PositiveSmallIntegerField(
        choices=SocialPostPriority.choices,
        default=SocialPostPriority.STANDARD,
    )
    status = models.CharField(
        max_length=24,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("posted", "Posted"),
            ("failed", "Failed"),
            ("throttled", "Throttled"),
        ],
    )
    error_code = models.CharField(max_length=64, blank=True, default="")
    external_post_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["school", "status", "priority", "created_at"],
                name="social_post_school__4c8f21_idx",
            ),
        ]


class SocialModerationItem(models.Model):
    """User-generated proud-campus moment awaiting staff approval."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="social_moderation_items",
    )
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="social_moments_submitted",
    )
    caption = models.CharField(max_length=500, blank=True, default="")
    image_url = models.URLField(max_length=2048)
    hashtag = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="social_moments_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["school", "status", "created_at"],
                name="social_mode_school__9d12ab_idx",
            ),
        ]


class SocialCampaignAttribution(models.Model):
    """Maps UTM-tagged inbound traffic to finance/donation events."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="social_campaign_attributions",
    )
    provider = models.CharField(max_length=32, choices=SocialProvider.choices)
    utm_source = models.CharField(max_length=120, blank=True, default="")
    utm_medium = models.CharField(max_length=120, blank=True, default="")
    utm_campaign = models.CharField(max_length=120, blank=True, default="")
    post_id = models.CharField(max_length=255, blank=True, default="")
    transaction_id = models.CharField(max_length=255, blank=True, default="")
    amount_cents = models.BigIntegerField(default=0)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["school", "provider", "recorded_at"],
                name="social_camp_school__e3a901_idx",
            ),
            models.Index(
                fields=["school", "utm_campaign"],
                name="social_camp_school__f2b110_idx",
            ),
        ]
