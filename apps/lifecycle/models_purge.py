"""Resumable, signed tenant-purge record (owner-decision b).

The existing purge command runs synchronously and leaves only a JSON manifest;
there is no resumable state, no signed proof of deletion, and sessions/tokens are
not revoked. PurgeOperation closes that:

- it is RESUMABLE — ``completed_phases`` records what's done so a re-run skips it;
- it SURVIVES the School being deleted — ``school_id``/``school_slug`` are PLAIN
  fields (no FK), which is the whole point: the record must outlive the tenant
  and stay idempotent after the School row is gone;
- it carries an HMAC-signed DELETION CERTIFICATE (see purge_certificate.py).

Lives in the lifecycle app (SHARED / public schema) so the control plane owns it.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class PurgeOperation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    RESUMABLE_STATUSES = (Status.PENDING, Status.RUNNING)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # PLAIN fields, no FK — must survive the School row being deleted.
    school_id = models.CharField(max_length=64, db_index=True)
    school_slug = models.CharField(max_length=255, db_index=True)

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purge_operations",
    )
    reason = models.CharField(max_length=255, blank=True)

    completed_phases = models.JSONField(default=list, blank=True)
    last_error = models.TextField(blank=True)

    row_total = models.PositiveIntegerField(default=0)
    schema_dropped = models.BooleanField(default=False)
    sessions_revoked = models.PositiveIntegerField(default=0)
    manifest_path = models.CharField(max_length=512, blank=True)

    # HMAC-signed deletion certificate (set on completion).
    certificate = models.JSONField(null=True, blank=True)
    certificate_signature = models.CharField(max_length=128, blank=True)
    certificate_signed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "lifecycle"
        db_table = "lifecycle_purgeoperation"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school_id", "status"]),
            models.Index(fields=["status", "-created_at"]),
        ]
        constraints = [
            # At most one non-terminal purge per school. Closes the
            # check-then-create race in begin_purge_operation so two concurrent
            # purges of one school can't mint duplicate operations/certificates;
            # the loser catches IntegrityError and reuses the winner's row.
            models.UniqueConstraint(
                fields=["school_id"],
                condition=models.Q(status__in=["pending", "running"]),
                name="uniq_active_purge_per_school",
            ),
        ]

    def __str__(self) -> str:
        return f"purge:{self.school_slug}:{self.status}"

    @property
    def needs_resume(self) -> bool:
        """A purge left in a non-terminal state must be picked up again."""
        return self.status in self.RESUMABLE_STATUSES

    def has_phase(self, phase: str) -> bool:
        return phase in (self.completed_phases or [])

    def add_phase(self, phase: str) -> None:
        phases = list(self.completed_phases or [])
        if phase not in phases:
            phases.append(phase)
        self.completed_phases = phases

    def mark_running(self, *, now=None) -> None:
        self.status = self.Status.RUNNING
        self.started_at = self.started_at or (now or timezone.now())

    def mark_failed(self, error: str) -> None:
        self.status = self.Status.FAILED
        self.last_error = str(error)[:4000]  # magic-number-allow: last-error-text-truncation-cap

    def mark_completed(self, *, now=None) -> None:
        self.status = self.Status.COMPLETED
        self.completed_at = now or timezone.now()
