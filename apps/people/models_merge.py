"""Record-merge operation of record (Wave C, design §4/D6).

One row per duplicate-consolidation: two person rows at the SAME school,
a previewed re-point plan, an explicit operator approval, and an applied
outcome whose collisions are QUARANTINED — never auto-deleted. The
secondary row is soft-retired (``is_active=False`` + ``merged_into``
tombstone where the model has one); nothing is ever hard-deleted.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class MergeStateError(Exception):
    """An illegal RecordMergeOperation transition was attempted."""


class RecordMergeOperation(models.Model):
    class Kind(models.TextChoices):
        STUDENT = "student", "Student"
        TEACHER = "teacher", "Teacher"
        GUARDIAN = "guardian", "Guardian link"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PREVIEWED = "previewed", "Previewed"
        APPROVED = "approved", "Approved"
        APPLYING = "applying", "Applying"
        APPLIED = "applied", "Applied"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    _TRANSITIONS: dict[str, frozenset[str]] = {
        Status.DRAFT: frozenset({Status.PREVIEWED, Status.CANCELLED}),
        Status.PREVIEWED: frozenset(
            {Status.APPROVED, Status.PREVIEWED, Status.CANCELLED}
        ),
        Status.APPROVED: frozenset({Status.APPLYING, Status.CANCELLED}),
        Status.APPLYING: frozenset({Status.APPLIED, Status.FAILED}),
        Status.APPLIED: frozenset(),
        Status.FAILED: frozenset(),
        Status.CANCELLED: frozenset(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="record_merge_operations",
    )
    kind = models.CharField(
        max_length=16, choices=Kind.choices, default=Kind.STUDENT, db_index=True
    )
    # Char PKs so the operation record outlives any future archival of the rows.
    primary_pk = models.CharField(max_length=64)
    secondary_pk = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    preview = models.JSONField(
        default=dict,
        blank=True,
        help_text="Re-point plan: per model.field row counts at preview time.",
    )
    collisions = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Quarantined unique-constraint hits from apply: rows left on the "
            "retired secondary for operator review — never deleted."
        ),
    )
    history = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merge_operations_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merge_operations_approved",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "people"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(primary_pk=models.F("secondary_pk")),
                name="record_merge_primary_neq_secondary",
            ),
        ]
        indexes = [models.Index(fields=["school", "status"])]

    def __str__(self) -> str:
        return f"RecordMergeOperation({self.kind} {self.secondary_pk} → {self.primary_pk} [{self.status}])"

    def advance(self, new_status: str, *, note: str = "") -> None:
        """Guarded transition — illegal moves raise, legal ones are journaled."""
        allowed = self._TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise MergeStateError(
                f"illegal merge transition {self.status!r} → {new_status!r}"
            )
        entry = {
            "from": self.status,
            "to": new_status,
            "at": timezone.now().isoformat(),
        }
        if note:
            entry["note"] = note[:500]
        self.history = [*(self.history or []), entry]
        self.status = new_status
        self.save(update_fields=["status", "history", "updated_at"])


__all__ = ["MergeStateError", "RecordMergeOperation"]
