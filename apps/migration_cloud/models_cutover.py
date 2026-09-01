"""CutoverRunbook — the rehearsal → real → sign-off record (audit G-3).

The competitive acceptance test for Migration Cloud is *"migration is done
when N districts' cutover runbook is executed and signed."* This module lands
the record that makes that statement checkable in code:

    draft → rehearsed (dry-run cutover) → executed (real cutover) → signed_off

A ``CutoverRunbook`` binds one district (``school``) to an optional
``rehearsal_bundle`` (the dry-run) and an optional ``real_bundle`` (the live
cutover), and captures the operator's sign-off — WHO signed, WHEN, their
verbatim ``signer_name`` / ``signer_title``, and an **integrity anchor**:
``reconciliation_scorecard_sha256``, the SHA-256 of the ``real_bundle``'s
reconciliation scorecard (``MigrationBundle.reconciliation_summary``) captured
at the instant of sign-off. If the scorecard is later mutated, the stored hash
no longer matches — so a sign-off can never silently drift away from the
numbers it was granted against.

Immutability discipline (mirrors ``MigrationAuthorizationAgreement``): once
``signed_off_at`` is set the sign-off is append-only. :meth:`record_signoff`
refuses a second sign-off, and :meth:`save` refuses to mutate any of the
sign-off anchor fields on an already-signed row.

Legal note: the sign-off *wording* / contractual force is LEGAL-EXTERNAL and
lives outside the codebase. This model is the record + hash + gate scaffolding
only — it does NOT assert or render binding legal text.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class CutoverRunbookError(Exception):
    """Base class for cutover-runbook workflow errors."""


class CutoverRunbookAlreadySignedError(CutoverRunbookError):
    """Raised when a runbook that already carries a sign-off is re-signed.

    The view layer surfaces this as an explicit 400 so the operator sees the
    refusal rather than a silent no-op (mirrors ``MAAAlreadyActiveError``).
    """


class CutoverRunbookNotReadyError(CutoverRunbookError):
    """Raised when sign-off is attempted before the runbook is signable.

    A runbook is signable only once a ``real_bundle`` is attached AND that
    bundle carries a non-empty reconciliation scorecard — you sign off *on* a
    reconciliation, so the numbers must exist first.
    """


class CutoverRunbookImmutableError(CutoverRunbookError):
    """Raised when a persisted, already-signed runbook's sign-off anchor
    fields are mutated. Defense-in-depth for the append-only contract."""


def compute_scorecard_sha256(scorecard: Any) -> str:
    """Return the SHA-256 hex of a reconciliation scorecard.

    Canonicalised the same way the audit hash-chain canonicalises its
    pre-image (``sort_keys`` + tight separators + ``ensure_ascii=False``) so
    the digest is stable across dict-ordering and Python versions. ``None`` /
    non-JSON-able input is coerced to ``{}`` so the helper never raises on a
    malformed summary — an anchor over an empty scorecard is still a valid
    (if weak) anchor, and :meth:`CutoverRunbook.record_signoff` separately
    refuses to sign an empty scorecard.
    """
    if not scorecard:
        scorecard = {}
    try:
        canonical = json.dumps(
            scorecard, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
    except (TypeError, ValueError):
        # Non-serialisable payload — fall back to its repr so a hash still
        # anchors *something* deterministic rather than raising.
        canonical = repr(scorecard)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CutoverRunbookStatus(models.TextChoices):
    """Lifecycle of a district cutover, from plan to signed record."""

    DRAFT = "draft", "Draft"
    REHEARSED = "rehearsed", "Rehearsed (dry-run cutover completed)"
    EXECUTED = "executed", "Executed (real cutover applied)"
    SIGNED_OFF = "signed_off", "Signed off"


class CutoverRunbook(models.Model):
    """One district's rehearsal → real → sign-off cutover record.

    The sign-off fields (``signed_off_*`` + ``reconciliation_scorecard_sha256``
    + terminal ``status``) are append-only once ``signed_off_at`` is set.
    """

    #: Sign-off anchor fields — locked once the runbook is signed.
    _SIGNOFF_ANCHOR_FIELDS = (
        "signed_off_at",
        "signed_off_by_id",
        "signer_name",
        "signer_title",
        "reconciliation_scorecard_sha256",
        "status",
    )

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="cutover_runbooks",
        help_text="The district this cutover runbook belongs to.",
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Operator-readable label (e.g. 'Sept 2026 district cutover').",
    )
    rehearsal_bundle = models.ForeignKey(
        "migration_cloud.MigrationBundle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cutover_runbooks_as_rehearsal",
        help_text="The dry-run bundle used to rehearse the cutover.",
    )
    real_bundle = models.ForeignKey(
        "migration_cloud.MigrationBundle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cutover_runbooks_as_real",
        help_text="The live cutover bundle whose reconciliation is signed off.",
    )
    status = models.CharField(
        max_length=16,
        choices=CutoverRunbookStatus.choices,
        default=CutoverRunbookStatus.DRAFT,
        db_index=True,
    )
    reconciliation_scorecard_sha256 = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=(
            "SHA-256 of the real_bundle's reconciliation scorecard "
            "(reconciliation_summary) captured at sign-off. Integrity anchor: "
            "a later scorecard mutation no longer matches this digest."
        ),
    )
    signed_off_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cutover_runbooks_signed",
        help_text="Operator who recorded the sign-off. NULL for system sign-offs.",
    )
    signed_off_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the sign-off was recorded. NULL until signed.",
    )
    signer_name = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="Verbatim name of the person signing off, captured at sign time.",
    )
    signer_title = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="Verbatim role/title of the signer, captured at sign time.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cutover_runbooks_created",
        help_text="Operator who created the runbook.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "migration_cloud"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]
        verbose_name = "Cutover runbook"
        verbose_name_plural = "Cutover runbooks"

    def __str__(self) -> str:
        return f"{self.label or 'Cutover'} [{self.status}] school={self.school_id}"

    @property
    def is_signed(self) -> bool:
        return self.signed_off_at is not None

    # ------------------------------------------------------------------
    # Append-only enforcement on the sign-off anchor fields.
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        """Refuse to mutate the sign-off anchor fields on a signed row.

        Non-anchor edits (``label``, bundle attachment BEFORE sign-off,
        ``updated_at``) remain allowed. The check only fires for a row that is
        ALREADY signed in the database, so the first sign-off save passes.
        """
        if self.pk is not None:
            prior = (
                type(self).objects  # tenant-isolation-allow: cutover-runbook-self-pk-readback-signoff-immutability-check
                .filter(pk=self.pk)
                .only(*self._SIGNOFF_ANCHOR_FIELDS)
                .first()
            )
            if prior is not None and prior.signed_off_at is not None:
                for fname in self._SIGNOFF_ANCHOR_FIELDS:
                    if getattr(self, fname) != getattr(prior, fname):
                        raise CutoverRunbookImmutableError(
                            "CutoverRunbook sign-off is append-only; the field "
                            f"{fname!r} cannot change after sign-off."
                        )
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Sign-off service method.
    # ------------------------------------------------------------------

    def record_signoff(
        self,
        *,
        user: Any = None,
        signer_name: str,
        signer_title: str = "",
    ) -> "CutoverRunbook":
        """Capture the operator's sign-off and anchor the scorecard hash.

        Computes ``reconciliation_scorecard_sha256`` from the ``real_bundle``'s
        reconciliation scorecard, stamps the signer, flips ``status`` to
        ``signed_off``, persists, and emits a ``migration.cutover.signed_off``
        lifecycle audit event via ``safe_bundle_audit`` (best-effort; an audit
        failure never rolls back the sign-off).

        Raises:
            CutoverRunbookAlreadySignedError: this runbook is already signed.
            CutoverRunbookNotReadyError: no ``real_bundle``, no reconciliation
                scorecard on it, or an empty ``signer_name``.
        """
        if self.is_signed:
            raise CutoverRunbookAlreadySignedError(
                "This cutover runbook has already been signed off."
            )
        if self.real_bundle_id is None:
            raise CutoverRunbookNotReadyError(
                "Attach the real cutover bundle before sign-off."
            )
        name = (signer_name or "").strip()
        if not name:
            raise CutoverRunbookNotReadyError("signer_name is required for sign-off.")

        scorecard = getattr(self.real_bundle, "reconciliation_summary", None) or {}
        if not scorecard:
            raise CutoverRunbookNotReadyError(
                "The real cutover bundle has no reconciliation scorecard yet; "
                "reconcile it before sign-off."
            )

        self.reconciliation_scorecard_sha256 = compute_scorecard_sha256(scorecard)
        self.signer_name = name[:256]
        self.signer_title = (signer_title or "").strip()[:256]
        self.signed_off_by = (
            user if user is not None and getattr(user, "pk", None) else None
        )
        self.signed_off_at = timezone.now()
        self.status = CutoverRunbookStatus.SIGNED_OFF
        self.save()

        self._emit_signoff_audit()
        return self

    def _emit_signoff_audit(self) -> None:
        """Emit the sign-off lifecycle audit event (best-effort, PII-free)."""
        try:
            from apps.migration_cloud.models_audit import MigrationCloudAuditEventType
            from apps.migration_cloud.services.bundle_lifecycle_audit import (
                safe_bundle_audit,
            )

            safe_bundle_audit(
                self.real_bundle,
                MigrationCloudAuditEventType.CUTOVER_SIGNED_OFF.value,
                payload_summary={
                    "cutover_runbook_id": self.pk,
                    "status": self.status,
                    "scorecard_sha256_prefix": self.reconciliation_scorecard_sha256[:12],
                    "signer_name_present": bool(self.signer_name),
                    "signer_title_present": bool(self.signer_title),
                    "real_bundle_id": self.real_bundle_id,
                    "rehearsal_bundle_id": self.rehearsal_bundle_id,
                },
            )
        except Exception:  # noqa: BLE001 — audit must never break sign-off
            logger.warning(
                "migration_cloud.cutover: sign-off audit emit failed runbook_id=%s",
                self.pk,
                exc_info=True,
            )


def cutover_signoff_pending_for_bundle(bundle) -> bool:
    """True when this bundle is the real cutover bundle awaiting operator sign-off."""
    if not bundle or not getattr(bundle, "pk", None):
        return False
    try:
        from apps.migration_cloud.models_cutover import (
            CutoverRunbook,
            CutoverRunbookStatus,
        )
    except ImportError:  # pragma: no cover
        return False
    # tenant-isolation-allow: bounded to one bundle by real_bundle_id, and a bundle is school-owned, so this cannot span tenants (both tenancy modes, reviewed 2026-09-01)
    return CutoverRunbook.objects.filter(
        real_bundle_id=bundle.pk,
    ).exclude(
        status=CutoverRunbookStatus.SIGNED_OFF,
        signed_off_at__isnull=False,
    ).exists()


__all__ = [
    "CutoverRunbook",
    "CutoverRunbookStatus",
    "CutoverRunbookError",
    "CutoverRunbookAlreadySignedError",
    "CutoverRunbookNotReadyError",
    "CutoverRunbookImmutableError",
    "compute_scorecard_sha256",
    "cutover_signoff_pending_for_bundle",
]
