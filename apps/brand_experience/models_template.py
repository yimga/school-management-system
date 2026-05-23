"""First-class TemplateAssignment + TemplateAuditEvent models.

Wave B residual (3 + 4): persistent customization state on ExperienceTemplate
applies + append-only audit trail. Both compose alongside the existing
``apps.packages.models.InstalledPackage`` / ``PackageChangeLog`` chain — they
do not replace it. ``TemplateAssignment`` is a OneToOne extension on
``InstalledPackage`` that carries template-specific customizations + the local
profile reference. ``TemplateAuditEvent`` is the append-only forensic trail
for template lifecycle events (preview / apply_requested / applied /
rolled_back / customized).

Append-only contract for ``TemplateAuditEvent`` follows the same
``AppendOnlyModelMixin`` + ``AppendOnlyManager`` pattern as
``apps.migration_cloud.models_audit.MigrationCloudAuditEvent``.
"""

from __future__ import annotations

import hashlib
import uuid

from django.db import models

from apps.platform_runtime.append_only import (
    AppendOnlyDeleteError,
    AppendOnlyManager,
    AppendOnlyModelMixin,
)


class TemplateAssignment(models.Model):
    """Per-school template assignment record extending InstalledPackage.

    OneToOne to ``packages.InstalledPackage`` so the underlying pack lifecycle
    record stays canonical. Adds template-specific fields: template_key,
    local_profile_key, surface, role_target, customizations (JSON), notes.
    """

    installed_package = models.OneToOneField(
        "packages.InstalledPackage",
        on_delete=models.CASCADE,
        related_name="template_assignment",
    )
    template_key = models.CharField(max_length=80, db_index=True)
    local_profile_key = models.CharField(max_length=80, blank=True, db_index=True)
    surface = models.CharField(max_length=32, blank=True)
    role_target = models.JSONField(default=list, blank=True)
    applied_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    rollback_snapshot = models.JSONField(default=dict, blank=True)
    customizations = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        app_label = "brand_experience"
        verbose_name = "Template Assignment"
        verbose_name_plural = "Template Assignments"
        indexes = [
            models.Index(fields=["template_key", "applied_at"]),
            models.Index(fields=["local_profile_key", "applied_at"]),
        ]

    def __str__(self) -> str:
        return f"TemplateAssignment({self.template_key}@{self.applied_at:%Y-%m-%d})"


_SENSITIVE_KEYS = {
    "password", "passwd", "pwd", "hash", "secret", "token",
    "ssn", "dob", "api_key", "apikey", "private_key",
    "signature_text", "email",
}


def _sanitize_payload(payload):
    """Walk a JSON-compatible dict and reject sensitive identifier keys.

    Returns a copy with sensitive keys removed; recurses through dicts and
    lists. Strings are never inspected — only key names.
    """
    if isinstance(payload, dict):
        clean = {}
        for k, v in payload.items():
            if str(k).strip().lower() in _SENSITIVE_KEYS:
                continue
            clean[k] = _sanitize_payload(v)
        return clean
    if isinstance(payload, list):
        return [_sanitize_payload(item) for item in payload]
    return payload


class TemplateAuditEventReadOnlyError(AppendOnlyDeleteError):
    """Raised when code attempts to mutate or delete a template audit row."""


class TemplateAuditEvent(AppendOnlyModelMixin, models.Model):
    """Append-only audit trail for ExperienceTemplate lifecycle events."""

    EVENT_TYPES = [
        ("template.preview", "Preview"),
        ("template.apply_requested", "Apply requested"),
        ("template.applied", "Applied"),
        ("template.rolled_back", "Rolled back"),
        ("template.customized", "Customized"),
        ("template.recommendation", "Recommendation"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id_hash = models.CharField(max_length=12, db_index=True)
    event_type = models.CharField(max_length=40, choices=EVENT_TYPES, db_index=True)
    template_key = models.CharField(max_length=80, db_index=True)
    local_profile_key = models.CharField(max_length=80, blank=True)
    actor_id = models.IntegerField(null=True, blank=True)
    payload_summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyManager()

    class Meta:
        app_label = "brand_experience"
        verbose_name = "Template Audit Event"
        verbose_name_plural = "Template Audit Events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id_hash", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["template_key", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise TemplateAuditEventReadOnlyError(
                "TemplateAuditEvent records are append-only and cannot be updated."
            )
        if isinstance(self.payload_summary, dict):
            self.payload_summary = _sanitize_payload(self.payload_summary)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"TemplateAuditEvent({self.event_type} {self.template_key} {self.created_at:%Y-%m-%dT%H:%M:%SZ})"


def hash_tenant_slug(slug: str) -> str:
    """Return sha256(slug)[:12] for PII-safe tenant identification in audit rows."""
    return hashlib.sha256((slug or "").encode("utf-8")).hexdigest()[:12]


def record_template_event(
    *,
    tenant_slug: str,
    event_type: str,
    template_key: str,
    local_profile_key: str = "",
    actor_id: int | None = None,
    payload: dict | None = None,
) -> TemplateAuditEvent:
    """Canonical write path for TemplateAuditEvent rows."""
    return TemplateAuditEvent.objects.create(
        tenant_id_hash=hash_tenant_slug(tenant_slug),
        event_type=event_type,
        template_key=template_key,
        local_profile_key=local_profile_key or "",
        actor_id=actor_id,
        payload_summary=payload or {},
    )
