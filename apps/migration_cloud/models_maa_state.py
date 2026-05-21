"""v3.40.0 Agent 15 — singleton model tracking the active MAA version.

This model persists the *flipped* state of the
``MAA_TEXT_DRAFT_VERSIONS`` set so the v2.0 promotion survives a worker
restart. Until v3.40 the set was a static module-level value, which
meant flipping v2.0 from DRAFT to ACTIVE required a code change. With
this row in place an operator with counsel signoff on file can perform
the flip atomically from the operator UI
(``apps.migration_cloud.views_maa_counsel_activate``).

Contract:
  * One singleton row enforced via a partial unique constraint on a
    helper ``_singleton`` boolean column.
  * ``active_version`` defaults to ``"v1.0"``. When a counsel
    activation succeeds the operator's view rewrites it to ``"v2.0"``
    and removes ``"v2.0"`` from the in-process draft set (via
    ``maa_text.refresh_draft_set_from_db()``).
  * ``activate_v2`` is the canonical mutator. It is intentionally
    idempotent (re-activating v2.0 raises :class:`MAAAlreadyActiveError`
    so the operator sees the explicit failure, never a silent no-op).
  * NEVER logs raw counsel_attestation_text — only its sha256 prefix.

Audit:
  * The mutation emits a ``migration.maa.v2_activated_by_operator``
    audit event with PII-free payload. Counsel attestation text raw is
    discarded after hashing.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

if TYPE_CHECKING:  # pragma: no cover — typing-only import
    pass

logger = logging.getLogger(__name__)


class MAAAlreadyActiveError(Exception):
    """Raised when ``activate_v2`` is called but v2.0 is already active.

    The view layer catches this and renders a 400 with an explicit
    explanation; the underlying mutation is a no-op so the operator's
    second click never advances the audit chain twice.
    """


class MAAActiveVersionState(models.Model):
    """Singleton row tracking the currently-active MAA version.

    The ``_singleton`` boolean + partial unique constraint enforces the
    "one row, ever" property at the database level.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    _singleton = models.BooleanField(
        default=True,
        editable=False,
        help_text="Always True; together with the partial unique index this enforces one-row-per-env.",
    )
    active_version = models.CharField(
        max_length=16,
        default="v1.0",
        help_text="The currently-binding MAA version. Defaults to v1.0.",
    )
    counsel_signoff_pdf_url = models.TextField(
        blank=True,
        null=True,
        help_text=(
            "URL the operator pasted in after counsel signed the v2.0 PDF. "
            "May contain a presigned token; NEVER logged."
        ),
    )
    counsel_attestation_sha256 = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text=(
            "sha256(counsel_attestation_text.encode('utf-8')) — fingerprint "
            "of the operator's verbatim attestation. Raw text is NEVER "
            "persisted; only the fingerprint."
        ),
    )
    counsel_attestation_name = models.CharField(
        max_length=256,
        blank=True,
        null=True,
        help_text="Full legal name of operator confirming counsel has signed.",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    activated_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maa_active_version_activations",
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Operator internal commentary; not surfaced to tenants.",
    )

    class Meta:
        app_label = "migration_cloud"
        verbose_name = "MAA active version state"
        verbose_name_plural = "MAA active version state"
        constraints = [
            models.UniqueConstraint(
                fields=["_singleton"],
                condition=models.Q(_singleton=True),
                name="maa_active_version_singleton",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover — repr only
        return f"MAAActiveVersionState(active={self.active_version})"

    # ──────────────────────────────────────────────────────────────────
    # Classmethods
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def get_row(cls) -> "MAAActiveVersionState":
        """Return the singleton row, creating it on first call.

        ``get_or_create`` is safe under the partial unique constraint —
        a race here returns whichever row won the insert; both have
        ``_singleton=True``.
        """
        # tenant-isolation-allow: platform-wide-maa-active-version-singleton
        row, _ = cls.objects.get_or_create(
            _singleton=True,
            defaults={"active_version": "v1.0"},
        )
        return row

    @classmethod
    def get_active_version(cls) -> str:
        """Return the currently-active version string.

        Defensive: returns ``"v1.0"`` if the row is somehow absent or
        the column is null. Never raises.
        """
        try:
            row = cls.get_row()
            return (row.active_version or "v1.0").strip() or "v1.0"
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "maa_active_version_state_unreadable err_type=%s",
                type(exc).__name__,
            )
            return "v1.0"

    @classmethod
    @transaction.atomic
    def activate_v2(
        cls,
        *,
        operator_user,
        counsel_pdf_url: str,
        attestation_name: str,
        attestation_text: str,
    ) -> "MAAActiveVersionState":
        """Flip the active version to ``v2.0`` atomically.

        Raises:
            MAAAlreadyActiveError: when v2.0 is already the active
                version. The view layer surfaces this as a 400.

        Side effects:
            * Persists the singleton row with the new active version.
            * Hashes the attestation text (raw text is NEVER stored).
            * Emits a ``migration.maa.v2_activated_by_operator`` audit
              event. The emit is best-effort — a DB failure on the
              audit side does NOT roll back the version flip (the
              chain-verifier will surface the gap).
        """
        row = cls.get_row()
        if (row.active_version or "").strip() == "v2.0":
            raise MAAAlreadyActiveError(
                "MAA v2.0 is already the active version on this environment."
            )

        attestation_sha = hashlib.sha256(
            (attestation_text or "").encode("utf-8"),
        ).hexdigest()

        row.active_version = "v2.0"
        row.counsel_signoff_pdf_url = counsel_pdf_url
        row.counsel_attestation_sha256 = attestation_sha
        row.counsel_attestation_name = (attestation_name or "")[:256]
        row.activated_at = timezone.now()
        row.activated_by_user = operator_user
        row.save()

        # Best-effort audit emit. We import lazily so this module stays
        # importable when models_audit is mid-migration in a fresh DB.
        try:
            from apps.migration_cloud.models_audit import (
                MigrationCloudAuditEvent,
            )

            operator_user_id = getattr(operator_user, "pk", None)
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="__platform__",
                event_type="migration.maa.v2_activated_by_operator",
                actor=operator_user,
                subject=None,
                payload_summary={
                    "operator_user_id": int(operator_user_id)
                    if operator_user_id is not None
                    else None,
                    "counsel_signoff_pdf_present": bool(counsel_pdf_url),
                    "counsel_attestation_name_len": len(
                        attestation_name or ""
                    ),
                    "counsel_attestation_fingerprint": attestation_sha[:12],
                    "activated_at_iso": (
                        row.activated_at.isoformat()
                        if row.activated_at
                        else None
                    ),
                },
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "maa_active_version_state_audit_emit_failed err_type=%s",
                type(exc).__name__,
            )

        logger.info(
            "maa_active_version_state_activated v2.0 user_id=%s attestation_sha_prefix=%s",
            getattr(operator_user, "pk", None),
            attestation_sha[:12],
        )
        return row


__all__ = [
    "MAAActiveVersionState",
    "MAAAlreadyActiveError",
]
