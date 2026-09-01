"""Persisted operator actions on the Edge Onboarding Runbook (control-plane only).

Append-only observability: skip-reason recordings and readiness snapshots.
Never stores secrets, emails, or slugs in ``payload`` (lifecycle sanitizer).
"""

from __future__ import annotations

import uuid

from django.db import models


class EdgeOnboardingRun(models.Model):
    class Kind(models.TextChoices):
        PREVIEW = "preview", "Readiness preview"
        SKIP_MC = "skip_mc", "Migration Cloud skip reason"
        SKIP_BACKUP = "skip_backup", "Box backup skip reason"
        SKIP_ASPECT = "skip_aspect", "Infrastructure aspect skip reason"
        VERIFY = "verify", "Box-side verify snapshot"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="edge_onboarding_runs",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, db_index=True)
    actor_hash = models.CharField(max_length=12, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["school", "-created_at"]),
            models.Index(fields=["kind", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"EdgeOnboardingRun({self.kind}#{self.pk})"
