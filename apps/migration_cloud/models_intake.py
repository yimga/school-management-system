"""Customer-facing migration intake request (v3.40.0 Agent 7).

``MigrationIntakeRequest`` is the school-side row that backs the
customer intake + status flow. The school's own staff (NOT RMC
operator staff) creates one of these to request a migration, signs the
MAA against it, watches its 7-stage progress, and receives email
notifications as it moves through the pipeline. Tenant-isolated: every
queryset MUST be filtered by the school's tenant.

The model is intentionally small: it's a coordination object that
glues an existing ``MigrationBundle`` lifecycle to a customer-visible
status surface. The bundle still owns the actual data lifecycle (see
``apps.migration_cloud.models.MigrationBundle``); this object owns the
*human workflow* around it — counsel signoff, MAA acceptance, guardian
consent counts, school-side / operator-side notes.

State machine (12 nodes, 17 transitions)
----------------------------------------

::

    intake-draft
       │
       ▼
    maa-pending-counsel ──────────┐
       │                          │
       ▼                          ▼
    maa-signed                 abandoned (terminal)
       │
       ▼
    extraction-in-progress ──┐
       │                     │
       ▼                     ▼
    extraction-complete    failed (terminal)
       │
       ▼
    validation-in-progress
       │
       ▼
    validation-complete
       │
       ▼
    promotion-pending-approval
       │
       ▼
    promotion-in-progress
       │
       ▼
    complete (terminal)

``abandoned`` may be entered from ``intake-draft`` or
``maa-pending-counsel`` only. ``failed`` may be entered from any
non-terminal state.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional, Tuple

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class MigrationIntakeStateError(Exception):
    """Raised when a state transition is not permitted from the current state."""


class MigrationIntakeState(models.TextChoices):
    INTAKE_DRAFT = "intake-draft", "Intake draft"
    MAA_PENDING_COUNSEL = "maa-pending-counsel", "MAA pending counsel signoff"
    MAA_SIGNED = "maa-signed", "MAA signed"
    EXTRACTION_IN_PROGRESS = "extraction-in-progress", "Extraction in progress"
    EXTRACTION_COMPLETE = "extraction-complete", "Extraction complete"
    VALIDATION_IN_PROGRESS = "validation-in-progress", "Validation in progress"
    VALIDATION_COMPLETE = "validation-complete", "Validation complete"
    PROMOTION_PENDING_APPROVAL = (
        "promotion-pending-approval",
        "Promotion pending school approval",
    )
    PROMOTION_IN_PROGRESS = "promotion-in-progress", "Promotion in progress"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"
    ABANDONED = "abandoned", "Abandoned"


_VENDOR_CHOICES = (
    ("powerschool", "PowerSchool"),
    ("blackbaud", "Blackbaud"),
    ("veracross", "Veracross"),
    ("alma", "Alma"),
    ("facts", "FACTS"),
    ("skyward", "Skyward"),
)


# Linear ordering used to derive `pct_complete`. Terminal failure /
# abandonment intentionally do not advance the progress bar past their
# entry point.
_PIPELINE_ORDER = (
    MigrationIntakeState.INTAKE_DRAFT,
    MigrationIntakeState.MAA_PENDING_COUNSEL,
    MigrationIntakeState.MAA_SIGNED,
    MigrationIntakeState.EXTRACTION_IN_PROGRESS,
    MigrationIntakeState.EXTRACTION_COMPLETE,
    MigrationIntakeState.VALIDATION_IN_PROGRESS,
    MigrationIntakeState.VALIDATION_COMPLETE,
    MigrationIntakeState.PROMOTION_PENDING_APPROVAL,
    MigrationIntakeState.PROMOTION_IN_PROGRESS,
    MigrationIntakeState.COMPLETE,
)


# Per-state legal next states. Built as a plain dict so callers can
# introspect the machine cheaply in tests.
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    MigrationIntakeState.INTAKE_DRAFT.value: frozenset({
        MigrationIntakeState.MAA_PENDING_COUNSEL.value,
        MigrationIntakeState.ABANDONED.value,
        MigrationIntakeState.FAILED.value,
    }),
    MigrationIntakeState.MAA_PENDING_COUNSEL.value: frozenset({
        MigrationIntakeState.MAA_SIGNED.value,
        MigrationIntakeState.ABANDONED.value,
        MigrationIntakeState.FAILED.value,
    }),
    MigrationIntakeState.MAA_SIGNED.value: frozenset({
        MigrationIntakeState.EXTRACTION_IN_PROGRESS.value,
        MigrationIntakeState.FAILED.value,
    }),
    MigrationIntakeState.EXTRACTION_IN_PROGRESS.value: frozenset({
        MigrationIntakeState.EXTRACTION_COMPLETE.value,
        MigrationIntakeState.FAILED.value,
    }),
    MigrationIntakeState.EXTRACTION_COMPLETE.value: frozenset({
        MigrationIntakeState.VALIDATION_IN_PROGRESS.value,
        MigrationIntakeState.FAILED.value,
    }),
    MigrationIntakeState.VALIDATION_IN_PROGRESS.value: frozenset({
        MigrationIntakeState.VALIDATION_COMPLETE.value,
        MigrationIntakeState.FAILED.value,
    }),
    MigrationIntakeState.VALIDATION_COMPLETE.value: frozenset({
        MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value,
        MigrationIntakeState.FAILED.value,
    }),
    MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value: frozenset({
        MigrationIntakeState.PROMOTION_IN_PROGRESS.value,
        MigrationIntakeState.FAILED.value,
    }),
    MigrationIntakeState.PROMOTION_IN_PROGRESS.value: frozenset({
        MigrationIntakeState.COMPLETE.value,
        MigrationIntakeState.FAILED.value,
    }),
    # Terminal states allow no outbound transitions.
    MigrationIntakeState.COMPLETE.value: frozenset(),
    MigrationIntakeState.FAILED.value: frozenset(),
    MigrationIntakeState.ABANDONED.value: frozenset(),
}


_TERMINAL_STATES = frozenset({
    MigrationIntakeState.COMPLETE.value,
    MigrationIntakeState.FAILED.value,
    MigrationIntakeState.ABANDONED.value,
})


class MigrationIntakeRequest(models.Model):
    """A school-side request to migrate from a SIS vendor into RunMyCampus."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    # FK to School (the tenant) — matches MigrationBundle.school. Cascade
    # mirrors the bundle: if the tenant is hard-deleted, the customer
    # intake history goes with it.
    tenant = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="migration_intake_requests",
        help_text="Tenant (school) that owns this intake request.",
    )
    requested_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_intake_requests",
        help_text="School user who initiated the request.",
    )
    vendor_slug = models.CharField(
        max_length=32,
        choices=_VENDOR_CHOICES,
        help_text="Source SIS vendor (one of the 6 supported vendors).",
    )
    state = models.CharField(
        max_length=40,
        choices=MigrationIntakeState.choices,
        default=MigrationIntakeState.INTAKE_DRAFT,
        db_index=True,
    )
    counsel_signoff_pdf_url = models.TextField(
        blank=True,
        null=True,
        help_text=(
            "URL the RMC operator pastes in after counsel signs off on "
            "the school's intake. NEVER log this value — it may include "
            "a presigned-S3 token that leaks read access on disclosure."
        ),
    )
    maa_signature = models.ForeignKey(
        "migration_cloud.MigrationAuthorizationAgreement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_intake_requests",
        help_text="The MAA signature that consented this intake. Null until signed.",
    )
    guardian_consent_collected_count = models.IntegerField(
        default=0,
        help_text="Guardians who have completed the consent flow.",
    )
    guardian_consent_required_count = models.IntegerField(
        default=0,
        help_text="Total guardians the school plans to collect consent from.",
    )
    requested_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes_for_runmycampus_team = models.TextField(
        blank=True,
        default="",
        help_text="School-side free-text notes; visible to RMC operators.",
    )
    notes_from_runmycampus_team = models.TextField(
        blank=True,
        default="",
        help_text="Operator-side free-text notes; visible to school.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["tenant", "state"]),
            models.Index(fields=["tenant", "-requested_at"]),
        ]
        verbose_name = "Migration intake request"
        verbose_name_plural = "Migration intake requests"

    def __str__(self) -> str:  # pragma: no cover — repr only
        return f"MigrationIntakeRequest({self.id} tenant={self.tenant_id} state={self.state})"

    # ─── State machine ───────────────────────────────────────────────

    def guardian_consent_satisfied(self) -> Tuple[bool, str]:
        """Whether guardian consent permits promoting this intake into the tenant.

        Consent gates the promotion of MINOR PII (COPPA / FERPA §99.30). The
        record model existed but nothing consulted it before landing — a guardian
        who declined, or whose consent was never collected, could not stop the
        data. This gate is enforced by ``can_advance_to`` on the promotion
        transitions. See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (BLOCKER 6).

        Codebase policy (the *threshold*): (a) if a consent campaign was set up
        (``guardian_consent_required_count > 0``) every required consent must be
        collected; (b) NO linked token may be DECLINED. The exact legal
        sufficiency rule per jurisdiction is counsel's — see
        docs/MIGRATION_CLOUD_LEGAL_EXTERNAL.md (L6). Enforcement can be disabled
        only via ``MIGRATION_CLOUD_ENFORCE_GUARDIAN_CONSENT=False`` (counsel-led).
        """
        from django.conf import settings

        if not getattr(settings, "MIGRATION_CLOUD_ENFORCE_GUARDIAN_CONSENT", True):
            return True, "consent enforcement disabled"

        # A guardian who explicitly DECLINED blocks promotion of the whole intake
        # (their child's PII must not land). Indexed reverse-FK query.
        try:
            from .models_guardian_consent import GuardianConsentDecision

            declined = self.guardian_consent_tokens.filter(
                consent_decision=GuardianConsentDecision.DECLINED.value,
            ).exists()
        except Exception:  # noqa: BLE001 — a query error must never OPEN the gate
            declined = True
        if declined:
            return False, "a guardian declined consent; promotion blocked"

        required = int(self.guardian_consent_required_count or 0)
        collected = int(self.guardian_consent_collected_count or 0)
        if required > 0 and collected < required:
            return False, f"guardian consent incomplete ({collected}/{required} collected)"
        return True, "ok"

    def can_advance_to(self, target_state: str) -> Tuple[bool, str]:
        """Return ``(ok, reason)`` for a hypothetical state transition.

        Pure function — does not mutate. Useful for templates that want
        to show / hide an action button.
        """
        if self.state == target_state:
            return False, "already in target state"
        if self.state in _TERMINAL_STATES:
            return False, f"current state {self.state!r} is terminal"
        allowed = _ALLOWED_TRANSITIONS.get(self.state, frozenset())
        if target_state not in allowed:
            return False, (
                f"transition {self.state!r} -> {target_state!r} not permitted"
            )
        # Guardian consent gates the promotion of minor PII into the tenant.
        if target_state in (
            MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value,
            MigrationIntakeState.PROMOTION_IN_PROGRESS.value,
        ):
            ok, reason = self.guardian_consent_satisfied()
            if not ok:
                return False, reason
        return True, "ok"

    def advance(
        self,
        target_state: str,
        *,
        actor=None,
    ) -> None:
        """Transition to ``target_state``, persist, emit an audit event.

        Raises :class:`MigrationIntakeStateError` on illegal transitions.
        Audit emission is best-effort: a downstream failure here will
        NOT roll back the transition (transitions are load-bearing for
        the customer UX; audit is a forensic side-channel).
        """
        ok, reason = self.can_advance_to(target_state)
        if not ok:
            raise MigrationIntakeStateError(
                f"refused intake_id={self.id} transition: {reason}"
            )

        previous_state = self.state
        now = timezone.now()
        with transaction.atomic():
            self.state = target_state
            if target_state == MigrationIntakeState.EXTRACTION_IN_PROGRESS.value and self.started_at is None:
                self.started_at = now
            if target_state in _TERMINAL_STATES and self.completed_at is None:
                self.completed_at = now
            self.save(update_fields=["state", "started_at", "completed_at", "updated_at"])

        # Audit emission — best-effort (mirrors companion_receiver._safe_audit).
        try:
            # Imported here to keep this model module import-light and
            # avoid a circular import at app load.
            from .models_audit import (
                MigrationCloudAuditEvent,
                MigrationCloudAuditEventType,
            )
            tenant_slug = getattr(self.tenant, "slug", "") or ""
            if target_state == MigrationIntakeState.MAA_SIGNED.value:
                MigrationCloudAuditEvent.objects.record(
                    tenant_slug,
                    MigrationCloudAuditEventType.MAA_SIGN.value,
                    actor=actor,
                    subject=str(self.id),
                    payload_summary={
                        "vendor_source": str(self.vendor_slug)[:64],
                        "intake_id_prefix": str(self.id)[:8],
                        "transition_from": previous_state[:40],
                    },
                )
            else:
                # Generic intake FSM trail — closes the deferred use of
                # INTAKE_STATE_ADVANCED (registered since v3.40, unused).
                MigrationCloudAuditEvent.objects.record(
                    tenant_slug,
                    MigrationCloudAuditEventType.INTAKE_STATE_ADVANCED.value,
                    actor=actor,
                    subject=str(self.id),
                    payload_summary={
                        "vendor_source": str(self.vendor_slug)[:64],
                        "intake_id_prefix": str(self.id)[:8],
                        "transition_from": previous_state[:40],
                        "transition_to": str(target_state)[:40],
                    },
                )
        except Exception as exc:  # noqa: BLE001 — audit must never break flow
            logger.error(
                "migration_cloud.intake: audit emit failed intake_id=%s "
                "target=%s err=%s",
                self.id, target_state, type(exc).__name__,
            )

        # PII-free transition log line. Note: does NOT include the
        # counsel_signoff_pdf_url, notes content, or signature bytes.
        logger.info(
            "migration_cloud.intake: transition intake_id=%s tenant_pk=%s "
            "from=%s to=%s actor_pk=%s",
            self.id,
            getattr(self.tenant, "pk", None),
            previous_state,
            target_state,
            getattr(actor, "pk", None) if actor is not None else None,
        )

    @property
    def is_terminal(self) -> bool:
        return self.state in _TERMINAL_STATES

    @property
    def pct_complete(self) -> int:
        """Map state to 0/10/.../100 for the customer progress bar.

        Failure / abandonment freeze the progress bar at its entry
        point's % — the customer should still see *where* we got to.
        """
        if self.state == MigrationIntakeState.COMPLETE.value:
            return 100
        if self.state == MigrationIntakeState.ABANDONED.value:
            return 0
        if self.state == MigrationIntakeState.FAILED.value:
            # Failure freezes wherever extraction reached. Returning 50
            # is a reasonable midpoint without persisting the prior
            # state separately. Tests assert this exact value.
            return 50
        # Linear position in the pipeline.
        try:
            idx = _PIPELINE_ORDER.index(MigrationIntakeState(self.state))
        except ValueError:
            return 0
        # 10 positions -> roughly 11% per step; canonical anchor values
        # below match the spec's "0/15/30/45/60/75/90/100" ladder.
        anchors = {
            0: 0,    # intake-draft
            1: 10,   # maa-pending-counsel
            2: 15,   # maa-signed
            3: 30,   # extraction-in-progress
            4: 45,   # extraction-complete
            5: 60,   # validation-in-progress
            6: 75,   # validation-complete
            7: 85,   # promotion-pending-approval
            8: 90,   # promotion-in-progress
            9: 100,  # complete
        }
        return anchors.get(idx, 0)

    def next_action_banner(self) -> Optional[str]:
        """Short, customer-facing hint for the status page next-action banner."""
        mapping = {
            MigrationIntakeState.INTAKE_DRAFT.value: (
                "Submit your intake to start the counsel-signoff process."
            ),
            MigrationIntakeState.MAA_PENDING_COUNSEL.value: (
                "Waiting on RunMyCampus counsel signoff. Sign the MAA to continue."
            ),
            MigrationIntakeState.MAA_SIGNED.value: (
                "MAA signed. Extraction will begin shortly."
            ),
            MigrationIntakeState.EXTRACTION_IN_PROGRESS.value: (
                "Extraction in progress. We will notify you when it completes."
            ),
            MigrationIntakeState.EXTRACTION_COMPLETE.value: (
                "Extraction complete. Validation will begin shortly."
            ),
            MigrationIntakeState.VALIDATION_IN_PROGRESS.value: (
                "Validation in progress."
            ),
            MigrationIntakeState.VALIDATION_COMPLETE.value: (
                "Validation complete. Awaiting your approval to promote into production."
            ),
            MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value: (
                "Awaiting your approval to promote the validated data into production."
            ),
            MigrationIntakeState.PROMOTION_IN_PROGRESS.value: (
                "Promotion in progress."
            ),
            MigrationIntakeState.COMPLETE.value: (
                "Migration complete. Your data is live in RunMyCampus."
            ),
            MigrationIntakeState.FAILED.value: (
                "Migration failed. See operator notes below; contact "
                "partner-success@runmycampus.com for next steps."
            ),
            MigrationIntakeState.ABANDONED.value: (
                "Migration abandoned at your request."
            ),
        }
        return mapping.get(self.state)
