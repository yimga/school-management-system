"""Public status page incidents (operator-curated, distinct from PlatformIncident)."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class PlatformStatusIncident(models.Model):
    """Curated incident visible on /status/ JSON and HTML."""

    class Status(models.TextChoices):
        INVESTIGATING = "investigating", "Investigating"
        IDENTIFIED = "identified", "Identified"
        MONITORING = "monitoring", "Monitoring"
        RESOLVED = "resolved", "Resolved"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    summary = models.TextField()
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.INVESTIGATING,
        db_index=True,
    )
    severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.MEDIUM,
        db_index=True,
    )
    component_keys = models.JSONField(
        default=list,
        blank=True,
        help_text="Component keys from public status payload (e.g. payments, auth).",
    )
    is_public = models.BooleanField(default=True, db_index=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_status_incidents_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at", "-created_at"]
        indexes = [
            models.Index(fields=["is_public", "status", "-started_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status != self.Status.RESOLVED
