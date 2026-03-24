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
        from apps.platform_runtime.helpers import (
            invalidate_effective_site_settings_cache,
        )

        invalidate_effective_site_settings_cache()
    except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass


class RuntimeDefaults(models.Model):
    """
    Platform-level default settings (migrated from SiteSettings).
    id=1 singleton; payload = JSON of attribute names -> values (JSON-serializable only).
    Step 4 ownership: first-class columns (e.g. cache_rankings_interval_minutes) override payload
    and SiteSettings when set; backfill via sync_from_site_settings / backfill_runtime_defaults.
    """

    payload = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Step 4: first-class ownership; when non-null, get_effective_site_settings uses this.
    cache_rankings_interval_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Owned by platform_runtime. When set, resolver uses this instead of SiteSettings.",
    )

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
                payload.update(
                    site_settings.owned_payload(owner=owner, exclude_owners=excluded)
                )
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
        # Step 4: backfill first-class owned field from SiteSettings
        cache_mins = getattr(site_settings, "cache_rankings_interval_minutes", None)
        defaults = {"payload": payload, "cache_rankings_interval_minutes": cache_mins}
        obj, created = cls.objects.get_or_create(
            pk=1,
            defaults=defaults,
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
            obj.cache_rankings_interval_minutes = cache_mins
            obj.save(
                update_fields=[
                    "payload",
                    "cache_rankings_interval_minutes",
                    "updated_at",
                ]
            )
        return obj, created

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.pk == 1:
            _invalidate_effective_site_settings_cache()


class PlatformPhaseBDomainSnapshot(models.Model):
    """
    Phase B Batches 4-13: one JSON snapshot per non-brand ownership domain.

    Rows mirror ``SiteSettings.owned_payload(owner=domain)`` on save (excluding
    ``sms_api_key`` for marketplace_integrations). ``get_effective_site_settings``
    merges these after ``RuntimeDefaults`` and before ``PlatformGlobalBranding``.
    """

    domain = models.CharField(max_length=64, primary_key=True)
    payload = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_phase_b_domain_snapshot"
        verbose_name = "Phase B domain snapshot"
        verbose_name_plural = "Phase B domain snapshots"

    def __str__(self) -> str:
        return self.domain


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


class PlatformEventLog(models.Model):
    """
    Append-only outbox for emit_platform_event (§0.3 Pillar 5 — event-driven baseline).
    Enables replay, analytics, and future webhook fan-out without losing events at log-only phase.
    """

    event_type = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    tenant_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    school_id = models.CharField(max_length=40, blank=True, default="", db_index=True)
    idempotency_key = models.CharField(
        max_length=128, blank=True, default="", db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Platform event log"
        verbose_name_plural = "Platform event logs"
        ordering = ["-created_at"]
