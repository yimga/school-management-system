"""School merge / split batch — the Wave D parent record (design §10).

A ``SchoolTransferBatch`` composes the proven Wave A–C rails: it fans out one
``TransferCase`` per eligible student (merge = the whole school, split = a
cohort) and rolls their outcomes up. It adds NO new transfer mechanics — every
case runs through the unmodified Wave B engine with all its guards.

Safety grammar is the purge path's: dual DISTINCT-operator approval with a
typed source-slug confirmation before anything runs, and wind-down is a
handoff to the EXISTING offboarding export + deactivate — the batch never
purges anything.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class BatchStateError(RuntimeError):
    """Raised on an illegal SchoolTransferBatch status transition."""


class SchoolTransferBatch(models.Model):
    """N student transfers from one school to another, driven as one operation."""

    class Kind(models.TextChoices):
        MERGE = "merge", "School merge (absorb source into target)"
        SPLIT = "split", "School split (cohort into a new tenant)"

    class ConsentMode(models.TextChoices):
        INSTITUTIONAL = "institutional", "Institutional authority (dual-approved)"
        PER_GUARDIAN = "per_guardian", "Per-guardian consent tokens"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PREVIEWED = "previewed", "Previewed"
        APPROVED = "approved", "Approved (dual)"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_ISSUES = "completed_with_issues", "Completed with issues"
        CANCELLED = "cancelled", "Cancelled"

    _TRANSITIONS: dict[str, frozenset[str]] = {
        Status.DRAFT: frozenset({Status.PREVIEWED, Status.CANCELLED}),
        # PREVIEWED → PREVIEWED journals the FIRST (primary) approval without
        # changing state — approval completes only on the second operator.
        Status.PREVIEWED: frozenset(
            {Status.PREVIEWED, Status.APPROVED, Status.CANCELLED}
        ),
        # APPROVED → PREVIEWED is the re-preview demotion: the population
        # changed since sign-off, so the batch drops back and approvals reset.
        Status.APPROVED: frozenset(
            {Status.RUNNING, Status.PREVIEWED, Status.CANCELLED}
        ),
        Status.RUNNING: frozenset(
            {
                Status.COMPLETED,
                Status.COMPLETED_WITH_ISSUES,
                Status.CANCELLED,
            }
        ),
        Status.COMPLETED: frozenset(),
        Status.COMPLETED_WITH_ISSUES: frozenset(),
        Status.CANCELLED: frozenset(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    source_school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="school_transfer_batches_out",
    )
    target_school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="school_transfer_batches_in",
    )
    consent_mode = models.CharField(
        max_length=20,
        choices=ConsentMode.choices,
        default=ConsentMode.INSTITUTIONAL,
    )
    consent_basis = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Institutional authority for the move (board resolution, ministry "
            "order…). Required before approval in institutional mode; journaled "
            "onto every case."
        ),
    )
    cohort = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Selection filter: {"classroom_ids": […], "student_pks": […]}. '
            "Empty = every active student (merge)."
        ),
    )
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.DRAFT
    )
    preview = models.JSONField(default=dict, blank=True)
    ledger = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-case attempt ledger: {case_id: {attempts, last_error, at}}.",
    )
    history = models.JSONField(default=list, blank=True)
    approved_by_primary = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="school_batches_approved_primary",
    )
    approved_by_secondary = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="school_batches_approved_secondary",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="school_batches_created",
    )
    wind_down = models.JSONField(
        default=dict,
        blank=True,
        help_text="Merge wind-down receipt: {export_zip, deactivated, at, by}.",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "people"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(source_school=models.F("target_school")),
                name="school_batch_source_neq_target",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "kind"]),
        ]

    def __str__(self) -> str:
        return f"SchoolTransferBatch {self.pk} [{self.kind}/{self.status}]"

    def advance(self, new_status: str, *, note: str = "") -> None:
        """Guarded transition — illegal moves raise, legal ones are journaled."""
        allowed = self._TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise BatchStateError(
                f"illegal batch transition {self.status!r} → {new_status!r}"
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


__all__ = ["BatchStateError", "SchoolTransferBatch"]
