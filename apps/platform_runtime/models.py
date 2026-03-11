"""
Phase 10 — 1.2: Runtime defaults (state-safe migration from SiteSettings).
Singleton row holds JSON snapshot of tenant-affecting settings; get_effective_site_settings
reads from here when present, falling back to SiteSettings for file fields and legacy.
"""
from __future__ import annotations

from django.db import models


class RuntimeDefaults(models.Model):
    """
    Platform-level default settings (migrated from SiteSettings).
    id=1 singleton; payload = JSON of attribute names -> values (JSON-serializable only).
    """
    payload = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Runtime defaults"
        verbose_name_plural = "Runtime defaults"

    @classmethod
    def get_singleton(cls) -> "RuntimeDefaults | None":
        return cls.objects.filter(pk=1).first()


class AIActionAuditLog(models.Model):
    """
    Phase 10 — 10.8: AI action audit trail.
    One row per AI-invoked action (e.g. suggestion accepted, content generated); for compliance and debugging.
    """
    action_type = models.CharField(max_length=80, db_index=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "AI action audit log"
        verbose_name_plural = "AI action audit logs"
        ordering = ["-created_at"]
