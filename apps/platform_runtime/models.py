"""
Phase 10 — 1.2: Runtime defaults (state-safe migration from SiteSettings).
Singleton row holds JSON snapshot of tenant-affecting settings; get_effective_site_settings
reads from here when present, falling back to SiteSettings for file fields and legacy.
"""
from __future__ import annotations

from django.db import models


def _invalidate_effective_site_settings_cache():
    """Called when RuntimeDefaults is saved so get_effective_site_settings sees new values."""
    try:
        from apps.platform_runtime.helpers import invalidate_effective_site_settings_cache
        invalidate_effective_site_settings_cache()
    except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass


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

    @classmethod
    def build_payload_from_site_settings(
        cls,
        site_settings,
        *,
        owners: list[str] | tuple[str, ...] | set[str] | None = None,
        exclude_owners: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> dict:
        """Build an ownership-filtered runtime payload from the legacy SiteSettings singleton."""
        owner_set = set(owners or [])
        excluded = set(exclude_owners or [])
        if owner_set:
            payload: dict = {}
            for owner in owner_set:
                payload.update(site_settings.owned_payload(owner=owner, exclude_owners=excluded))
            return payload
        return site_settings.owned_payload(exclude_owners=excluded)

    @classmethod
    def sync_from_site_settings(
        cls,
        site_settings,
        *,
        owners: list[str] | tuple[str, ...] | set[str] | None = None,
        exclude_owners: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> tuple["RuntimeDefaults", bool]:
        """Persist a filtered RuntimeDefaults payload from SiteSettings and return (object, created).
        Callers must pass site_settings (e.g. SiteSettings.get_solo() in commands, self in SiteSettings.save).
        B1 allowlist shrink: no get_solo() in this module."""
        owner_set = set(owners or [])
        payload = cls.build_payload_from_site_settings(
            site_settings,
            owners=owner_set,
            exclude_owners=exclude_owners,
        )
        obj, created = cls.objects.get_or_create(
            pk=1,
            defaults={"payload": payload},
        )
        if not created:
            if owner_set:
                merged_payload = dict(obj.payload or {})
                for owner in owner_set:
                    for field_name in site_settings.owned_field_names(owner=owner):
                        merged_payload.pop(field_name, None)
                merged_payload.update(payload)
                obj.payload = merged_payload
            else:
                obj.payload = payload
            obj.save(update_fields=["payload", "updated_at"])
        return obj, created

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.pk == 1:
            _invalidate_effective_site_settings_cache()


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
