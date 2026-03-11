"""
API Center: audit log for Integration toggles (unified with siteconfig.Integration); API keys for external developers.
"""
import hashlib
import secrets

from django.conf import settings
from django.db import models


def _hash_secret(secret: str) -> str:
    """One-way hash for storing API key secrets. Use constant-time compare for verification."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class APIKey(models.Model):
    """
    Tenant-scoped API key for external API authentication (8.1).
    Secret is shown only once at creation; only key_prefix and hash are stored.
    """

    PREFIX = "sk_live_"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="api_keys",
    )
    name = models.CharField(max_length=120, help_text="Label for this key (e.g. Production, CI)")
    key_prefix = models.CharField(max_length=24, editable=False)
    secret_hash = models.CharField(max_length=64, editable=False)
    scopes = models.JSONField(default=list, blank=True, help_text="Optional list of scope strings")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_api_keys",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "API Key"
        verbose_name_plural = "API Keys"

    def __str__(self):
        return f"{self.key_prefix}… ({self.name})"

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    @classmethod
    def generate_key_pair(cls):
        """Returns (key_prefix, raw_secret). Caller hashes raw_secret and stores key_prefix + hash."""
        raw = secrets.token_urlsafe(32)
        full_secret = cls.PREFIX + raw
        key_prefix = full_secret[: len(cls.PREFIX) + 8]
        return key_prefix, full_secret

    @classmethod
    def verify(cls, key_prefix: str, raw_secret: str) -> "APIKey | None":
        """Constant-time verify; returns APIKey if valid and not revoked."""
        secret_hash = _hash_secret(raw_secret)
        qs = cls.objects.filter(key_prefix=key_prefix, revoked_at__isnull=True)
        for obj in qs:
            if secrets.compare_digest(obj.secret_hash, secret_hash):
                return obj
        return None


class APIAuditLog(models.Model):
    """Audit trail for Integration enable/disable and other governance changes."""

    class Action(models.TextChoices):
        ENABLED = "enabled", "Enabled"
        DISABLED = "disabled", "Disabled"
        KEY_ROTATED = "key_rotated", "Key rotated"
        LIMIT_CHANGED = "limit_changed", "Limit changed"
        SCOPE_CHANGED = "scope_changed", "Scope changed"
        IP_UPDATED = "ip_updated", "IP list updated"

    integration = models.ForeignKey(
        "siteconfig.Integration",
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="api_audit_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    reason = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "API Audit Log"
        verbose_name_plural = "API Audit Logs"

    def __str__(self):
        return f"{self.get_action_display()} – {self.integration.slug} @ {self.created_at}"
