"""Inter-school transfer case — the state machine of record (Wave A).

Design: docs/TRANSFER_MERGE_SPLIT_ORCHESTRATOR_DESIGN.md §4-5. A TransferCase
tracks one student's move from source school to target school. Wave A ships
the model + guarded FSM; the orchestration runner, consent artifact, and
operator console arrive in Wave B, which is why ``consent_reference`` and
``target_bundle_id`` are loose references rather than FKs — the case must not
couple ``people`` to migration_cloud's schema.

Lives in ``apps.people`` (not ``apps.interop`` as the design doc's shorthand
suggested) because interop is not an installed Django app — it has no
migrations rail. The passport, the profile, and the case belong together.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TransferStateError(RuntimeError):
    """Raised on an illegal TransferCase status transition."""


class TransferCase(models.Model):
    """One student's source→target transfer, with an explicit, guarded FSM."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONSENT_PENDING = "consent_pending", "Consent pending"
        APPROVED = "approved", "Approved"
        EXPORTING = "exporting", "Exporting"
        ENVELOPE_SEALED = "envelope_sealed", "Envelope sealed"
        APPLYING = "applying", "Applying"
        APPLIED = "applied", "Applied"
        RECONCILED = "reconciled", "Reconciled"
        FAILED = "failed", "Failed"
        COMPENSATING = "compensating", "Compensating"
        CANCELLED = "cancelled", "Cancelled"

    _TRANSITIONS: dict[str, frozenset[str]] = {
        Status.DRAFT: frozenset({Status.CONSENT_PENDING, Status.CANCELLED}),
        Status.CONSENT_PENDING: frozenset({Status.APPROVED, Status.CANCELLED}),
        Status.APPROVED: frozenset({Status.EXPORTING, Status.CANCELLED}),
        Status.EXPORTING: frozenset({Status.ENVELOPE_SEALED, Status.FAILED}),
        Status.ENVELOPE_SEALED: frozenset(
            {Status.APPLYING, Status.FAILED, Status.CANCELLED}
        ),
        Status.APPLYING: frozenset(
            {Status.APPLIED, Status.FAILED, Status.COMPENSATING}
        ),
        Status.APPLIED: frozenset({Status.RECONCILED, Status.COMPENSATING}),
        Status.COMPENSATING: frozenset({Status.FAILED}),
        Status.RECONCILED: frozenset(),
        Status.FAILED: frozenset(),
        Status.CANCELLED: frozenset(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        "people.SchoolTransferBatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cases",
        help_text="School merge/split batch that fanned this case out (Wave D).",
    )
    passport = models.ForeignKey(
        "people.StudentPassport",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transfer_cases",
        help_text="Cross-school identity anchor for the student being moved.",
    )
    source_school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="transfer_cases_out",
    )
    target_school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="transfer_cases_in",
    )
    source_profile_pk = models.CharField(max_length=64)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    domains = models.JSONField(
        default=list,
        blank=True,
        help_text="Canonical domains included in this transfer.",
    )
    envelope_checksum = models.CharField(max_length=64, blank=True, default="")
    target_bundle_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Migration-cloud bundle applying this case at the target school.",
    )
    consent_reference = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Wave B consent artifact reference (kept loose deliberately).",
    )
    history = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transfer_cases_created",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "people"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(source_school=models.F("target_school")),
                name="transfer_case_source_neq_target",
            ),
        ]
        indexes = [
            models.Index(fields=["source_school", "status"]),
            models.Index(fields=["target_school", "status"]),
            # The batch advancer's hot query (D.1).
            models.Index(fields=["batch", "status"]),
        ]

    def __str__(self) -> str:
        return f"TransferCase {self.pk} [{self.status}]"

    def advance(self, new_status: str, *, note: str = "") -> None:
        """Guarded transition — illegal moves raise, legal ones are journaled."""
        allowed = self._TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise TransferStateError(
                f"illegal transfer transition {self.status!r} → {new_status!r}"
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


__all__ = ["TransferCase", "TransferStateError"]
