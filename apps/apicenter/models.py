"""
API Center: audit log for Integration toggles (unified with siteconfig.Integration).
"""
from django.conf import settings
from django.db import models


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
