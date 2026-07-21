"""v3.38.0 Agent 5 — Migration Cloud tamper-evident audit log.

`MigrationCloudAuditEvent` is the append-only forensic trail every
sensitive Migration Cloud event (companion upload, MAA sign attempt,
key rotation, webhook subscription mutation, webhook delivery replay,
scoped-token mint, scoped-token revoke, legacy-hash decrypt) writes
to. Auditors (FERPA / SOC2 reviewers; tenant operators) can export
the log as JSONL and verify its integrity hash-chain.

Design contract
---------------

  * **Append-only.** ``save()`` on an existing row raises
    :class:`MigrationCloudAuditEventReadOnlyError`. ``delete()``
    always raises. The manager refuses ``.update()`` /
    ``.bulk_create()`` (inherited from ``AppendOnlyManager``).
  * **Per-tenant hash chain.** Each event's ``integrity_hash`` is
    SHA-256 over a canonical-JSON of its fields PLUS the previous
    event's ``integrity_hash`` for the same tenant. The first event
    per tenant uses sentinel ``prev_event_hash = "genesis"``.
  * **No raw PII / secret material.** Tenant slug, user email,
    subject UUID are stored as SHA-256-derived hex prefixes only.
    Payload summaries are walked by ``_sanitize_payload`` and any
    sensitive-keyword identifier is REJECTED at write time.

Hash-chain semantics
--------------------

The canonical JSON pre-image is::

    {
      "id":              "<uuid-hex>",
      "tenant_id_hash":  "<12-hex>",
      "event_type":      "<name>",
      "actor_id":        "<64-hex-or-null>",
      "event_subject_hash": "<64-hex-or-null>",
      "payload_summary": <dict>,
      "created_at_iso":  "<ISO-8601-UTC>",
      "prev_event_hash": "<64-hex-or-genesis>"
    }

Canonical serialization: ``json.dumps(..., sort_keys=True,
separators=(",", ":"), ensure_ascii=False)``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from typing import Any

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.platform_runtime.append_only import (
    AppendOnlyDeleteError,
    AppendOnlyManager,
    AppendOnlyModelMixin,
)

logger = logging.getLogger(__name__)


class MigrationCloudAuditEventReadOnlyError(AppendOnlyDeleteError):
    """Raised when code tries to mutate or delete an audit event row."""


# ──────────────────────────────────────────────────────────────────────
# v3.40.0 Agent 14 — Per-tenant audit-event volume rate-limit.
#
# Threat: a runaway emit-loop (bad call site, malicious caller) writes
# millions of audit events into the append-only chain. Because rows are
# delete-blocked, the only mitigation is a guard at the write site.
#
# Implementation: module-level sliding-1h counter keyed by
# (tenant_id_hash, event_type). One meta-event written on first hit per
# hour per (tenant, event_type); subsequent hits raise the typed
# AuditEventRateLimitExceeded without writing.
#
# In-memory only — worker restart resets the counter (documented in
# docs/MIGRATION_CLOUD_AUDIT_RATE_LIMITING.md). Acceptable because the
# limit is a runaway-guard, not a hard cap.
# ──────────────────────────────────────────────────────────────────────


class AuditEventRateLimitExceeded(Exception):
    """Raised when a tenant/event-type pair exceeds the per-hour limit.

    Attributes
    ----------
    tenant_id_hash : str
        sha256(tenant_slug)[:12] of the offending tenant.
    event_type : str
        The audit event type that was rate-limited.
    count_in_window : int
        Observed event count in the sliding 1h window at refusal time.
    limit : int
        The active per-hour limit at refusal time.
    """

    def __init__(
        self,
        tenant_id_hash: str,
        event_type: str,
        count_in_window: int,
        limit: int,
    ) -> None:
        self.tenant_id_hash = tenant_id_hash
        self.event_type = event_type
        self.count_in_window = int(count_in_window)
        self.limit = int(limit)
        super().__init__(
            f"audit rate-limit exceeded tenant_hash={tenant_id_hash} "
            f"event_type={event_type} count={self.count_in_window} "
            f"limit={self.limit}"
        )


_RATE_LIMIT_LOCK = threading.Lock()
# Per (tenant_id_hash, event_type) → list[float] of monotonic emit timestamps
# within the last 1h. Pruned lazily on each access.
_RATE_LIMIT_BUCKETS: dict[tuple[str, str], list[float]] = {}
# Per tenant_id_hash → monotonic timestamp of last meta-event emit, to
# enforce one-meta-event-per-hour-per-tenant.
_RATE_LIMIT_META_LAST: dict[str, float] = {}


def _rate_limit_clock() -> float:
    """Monotonic clock — overridable by tests via patching."""
    return time.monotonic()


def _rate_limit_window_seconds() -> float:
    """1h sliding window — small helper for test injection."""
    return 3600.0


def _rate_limit_reset_for_tests() -> None:
    """Clear in-memory state. ONLY called by tests."""
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_BUCKETS.clear()
        _RATE_LIMIT_META_LAST.clear()


def _rate_limit_check_and_increment(
    tenant_id_hash: str, event_type: str,
) -> tuple[bool, int]:
    """Atomically: prune, check limit, increment.

    Returns
    -------
    (allowed, count_in_window)
        ``allowed`` is True if the write may proceed (counter
        incremented). False if the limit is exceeded (counter NOT
        incremented further beyond the observed count).
    """
    if bool(getattr(
        settings, "MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED", False,
    )):
        return True, 0
    limit = int(getattr(
        settings, "MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR",
        5000,
    ) or 5000)
    if limit <= 0:
        # Negative / zero limit is nonsensical; treat as disabled.
        return True, 0
    key = (tenant_id_hash, event_type)
    now = _rate_limit_clock()
    window = _rate_limit_window_seconds()
    with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_BUCKETS.get(key)
        if bucket is None:
            bucket = []
            _RATE_LIMIT_BUCKETS[key] = bucket
        # Prune entries older than the sliding window.
        cutoff = now - window
        if bucket and bucket[0] < cutoff:
            # Slice from the first index where ts >= cutoff.
            keep_from = 0
            for i, ts in enumerate(bucket):
                if ts >= cutoff:
                    keep_from = i
                    break
            else:
                keep_from = len(bucket)
            del bucket[:keep_from]
        if len(bucket) >= limit:
            return False, len(bucket)
        bucket.append(now)
        return True, len(bucket)


def _rate_limit_should_emit_meta(tenant_id_hash: str) -> bool:
    """One meta-event per tenant per hour. Bumps the last-emit ts."""
    now = _rate_limit_clock()
    window = _rate_limit_window_seconds()
    with _RATE_LIMIT_LOCK:
        last = _RATE_LIMIT_META_LAST.get(tenant_id_hash, 0.0)
        if (now - last) < window:
            return False
        _RATE_LIMIT_META_LAST[tenant_id_hash] = now
        return True


# Registered event-type constant for the meta-event. Declared as a
# module-level string so callers can reference it without importing the
# TextChoices enum below (avoids a forward-reference cycle).
_AUDIT_RATE_LIMIT_META_TYPE = "audit.rate_limit_triggered"


class MigrationCloudAuditEventType(models.TextChoices):
    """Canonical event-type constants for the audit log."""

    COMPANION_UPLOAD = "companion.upload", "Companion upload accepted"
    MAA_SIGN = "maa.sign", "MAA signed"
    MAA_SIGN_ATTEMPT_DRAFT = (
        "maa.sign_attempt_draft",
        "Attempt to sign a DRAFT MAA refused",
    )
    KEY_ROTATE = "key.rotate", "Companion server-keypair rotated"
    WEBHOOK_SUBSCRIPTION_CREATED = (
        "webhook.subscription.created",
        "Webhook subscription created",
    )
    WEBHOOK_SUBSCRIPTION_DELETED = (
        "webhook.subscription.deleted",
        "Webhook subscription deleted (deactivated)",
    )
    WEBHOOK_DELIVERY_REPLAY = (
        "webhook.delivery.replay",
        "Webhook delivery manually replayed",
    )
    TOKEN_MINT = "token.mint", "Scoped API token minted"
    TOKEN_REVOKE = "token.revoke", "Scoped API token revoked"
    LEGACY_HASH_DECRYPT = (
        "legacy_hash.decrypt",
        "Legacy SIS-hash field decrypted",
    )
    # v3.39.0 Agent 1 — meta-event written by the
    # ``purge_audit_events_pre_approved`` management command. The
    # purge itself is intentionally cross-tenant (raw-SQL DELETE
    # bypasses the append-only manager) so the meta-event lives in
    # the same audit table, audit-ing the purge.
    AUDIT_RETENTION_PURGE_APPLIED = (
        "audit.retention_purge_applied",
        "Audit retention purge applied (counsel-approved)",
    )
    # v3.40.0 Agent 11 — guardian-consent collection flow + intake
    # generic transition event. The intake-level state_advanced event
    # closes Agent 7's deferred item; the guardian.* set covers the
    # full FERPA/COPPA/GDPR-compatible consent lifecycle.
    INTAKE_STATE_ADVANCED = (
        "migration.intake.state_advanced",
        "Migration intake state advanced",
    )
    GUARDIAN_CONSENT_CAMPAIGN_STARTED = (
        "migration.guardian_consent.campaign_started",
        "Guardian consent campaign started",
    )
    GUARDIAN_CONSENT_MINTED = (
        "migration.guardian_consent.minted",
        "Guardian consent token minted",
    )
    GUARDIAN_CONSENT_FIRST_SEEN = (
        "migration.guardian_consent.first_seen",
        "Guardian opened the consent page for the first time",
    )
    GUARDIAN_CONSENT_CONSENTED = (
        "migration.guardian_consent.consented",
        "Guardian consented to migration",
    )
    GUARDIAN_CONSENT_DECLINED = (
        "migration.guardian_consent.declined",
        "Guardian declined consent",
    )
    GUARDIAN_CONSENT_REVOKED = (
        "migration.guardian_consent.revoked",
        "Guardian revoked previously-granted consent",
    )
    GUARDIAN_CONSENT_EXPIRED = (
        "migration.guardian_consent.expired",
        "Guardian consent token expired before decision",
    )
    GUARDIAN_CONSENT_RESENT = (
        "migration.guardian_consent.resent",
        "Guardian consent email resent",
    )
    # v3.40.0 Agent 14 — Per-tenant audit-event volume rate-limit
    # triggered. Written by AuditEventManager.record() when the
    # per-(tenant, event_type)-per-hour limit is exceeded. Capped at one
    # write per tenant per hour so the meta-event itself cannot run away.
    AUDIT_RATE_LIMIT_TRIGGERED = (
        "audit.rate_limit_triggered",
        "Audit event volume rate-limit triggered for a tenant",
    )
    # v3.40.0 Agent 15 — MAA v2.0 counsel-review activation flip.
    # Emitted by ``MAAActiveVersionState.activate_v2`` when an operator
    # with counsel signoff on file advances the platform default from
    # v1.0 to v2.0. Payload contains operator_user_id + attestation
    # fingerprint prefix + activated_at; raw attestation text is
    # NEVER logged.
    MAA_V2_ACTIVATED_BY_OPERATOR = (
        "migration.maa.v2_activated_by_operator",
        "MAA v2.0 activated by operator (counsel signoff on file)",
    )
    # v3.40.0 Agent 15 — Migration data retention purge applied.
    # Emitted by ``purge_completed_migration_bundles`` command on
    # --apply. PII-free payload (tenant_sha256_prefix + counts only).
    MIGRATION_DATA_RETENTION_PURGE_APPLIED = (
        "migration.data_retention.purge_applied",
        "Migration data retention purge applied (counsel-approved)",
    )
    # v3.61.6 Wave L6 — lifecycle.* mirror types written by
    # apps.lifecycle.services_offboarding.audit_event_mirror. Closes the
    # L4 honest deferral that left offboarding-event mirroring as
    # structured-log-only because the audit enum was closed. Each value
    # corresponds 1:1 to a SchoolProvisioningEvent offboarding type,
    # giving offboarding event the same hash-chain integrity guarantees
    # as Migration Cloud's intake events.
    LIFECYCLE_OFFBOARDING_EXPORT = (
        "lifecycle.offboarding.export",
        "School offboarding data export generated",
    )
    LIFECYCLE_OFFBOARDING_DEACTIVATED = (
        "lifecycle.offboarding.deactivated",
        "School deactivated (offboarding)",
    )
    LIFECYCLE_OFFBOARDING_PURGE_REQUESTED = (
        "lifecycle.offboarding.purge_requested",
        "School offboarding purge requested",
    )
    LIFECYCLE_OFFBOARDING_PURGE_COMPLETED = (
        "lifecycle.offboarding.purge_completed",
        "School offboarding purge completed",
    )
    # Bundle pipeline / apply trail (tenant Dominance audit §0.6).
    # Companion upload/decrypt already emit; advance+apply were the gap.
    BUNDLE_ADVANCED = (
        "migration.bundle.advanced",
        "Migration bundle advanced through profile/classify/map",
    )
    BUNDLE_APPLIED = (
        "migration.bundle.applied",
        "Migration bundle apply completed (live or dry-run)",
    )


GENESIS_SENTINEL = "genesis"


_SENSITIVE_KEYS = (
    "password",
    "passwd",
    "pwd",
    "hash",
    "secret",
    "token",
    "ssn",
    "dob",
    "api_key",
    "apikey",
    "private_key",
    "signature_text",
    "email",
    "slug",
)


def _hash_tenant_slug(tenant_slug: str) -> str:
    """First 12 hex chars of SHA-256(tenant_slug).

    Matches Agent 4's ``_hash_tenant_id`` helper at
    ``apps/migration_cloud/metrics.py``; replicated here so the audit
    log is independent of the metrics module's load order. If Agent 4
    is loaded first, both helpers produce the same prefix.
    """
    if tenant_slug is None:
        tenant_slug = ""
    return hashlib.sha256(tenant_slug.encode("utf-8")).hexdigest()[:12]


def _hash_email_or_id(value: Any) -> str | None:
    """Return ``sha256(str(value))[:64]`` for non-empty input, else None."""
    if value is None or value == "":
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:64]


def _key_looks_sensitive(key: str) -> bool:
    """True if a dict key is in the rejection list (case-insensitive substring).

    Domain-neutral substrings like 'hashlib' are not a concern here —
    this is a JSON-payload key check, not a Python identifier check.
    """
    if not isinstance(key, str):
        return False
    k = key.lower()
    for needle in _SENSITIVE_KEYS:
        if needle in k:
            return True
    return False


def _sanitize_payload(summary: Any) -> dict:
    """Validate that ``summary`` contains no sensitive-keyword keys.

    Walks dicts + lists recursively. Raises ``ValueError`` if any key
    matches the rejection list. Returns the (unchanged) dict on
    success so callers can write the sanitized value back.

    Non-dict top-level inputs are coerced: ``None`` → ``{}``; anything
    else is wrapped as ``{"value": ...}`` (a defensive shape; payloads
    SHOULD always be dicts on the way in).
    """
    if summary is None:
        return {}
    if not isinstance(summary, dict):
        # Defensive — log + coerce, never raise on shape. The key
        # rejection is the real defense.
        logger.warning(
            "migration_cloud.audit: _sanitize_payload non-dict input "
            "coerced type=%s", type(summary).__name__,
        )
        summary = {"value": summary}

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if _key_looks_sensitive(k):
                    raise ValueError(
                        "audit payload_summary rejected: key "
                        f"{path + '.' + k!r} matches sensitive-keyword list"
                    )
                _walk(v, path + "." + str(k))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _walk(item, path + f"[{i}]")
        # Scalars (int, str, bool, float, None) are allowed.

    _walk(summary, "")
    return summary


def _canonical_json(obj: dict) -> bytes:
    """Stable JSON encoding for hash-chain pre-image."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _compute_integrity_hash(
    *,
    pk: str,
    tenant_id_hash: str,
    event_type: str,
    actor_id: str | None,
    event_subject_hash: str | None,
    payload_summary: dict,
    created_at_iso: str,
    prev_event_hash: str,
) -> str:
    """Return SHA-256 hex of the canonical-JSON pre-image."""
    pre = {
        "id": pk,
        "tenant_id_hash": tenant_id_hash,
        "event_type": event_type,
        "actor_id": actor_id,
        "event_subject_hash": event_subject_hash,
        "payload_summary": payload_summary,
        "created_at_iso": created_at_iso,
        "prev_event_hash": prev_event_hash,
    }
    return hashlib.sha256(_canonical_json(pre)).hexdigest()


class AuditEventManager(AppendOnlyManager):
    """Canonical write path for audit events.

    Use :meth:`record` exclusively. ``.create()`` works too (the
    overridden ``save()`` populates the chain), but ``record()`` is
    the documented surface that operator code should call.
    """

    def record(
        self,
        tenant_slug: str,
        event_type: str,
        *,
        actor: Any = None,
        subject: Any = None,
        payload_summary: dict | None = None,
    ):
        """Append one event. Returns the persisted instance.

        ``actor`` may be a User instance (uses ``.email``), a string
        (used directly), or None. ``subject`` may be any identifier
        (UUID, int, slug); it's coerced to str then hashed. The
        payload is sanitized before write.
        """
        # Validate event_type early — TextChoices lookup.
        valid = {c.value for c in MigrationCloudAuditEventType}
        if event_type not in valid:
            raise ValueError(
                f"audit event_type {event_type!r} not in registered choices"
            )

        actor_value: Any
        if actor is None:
            actor_value = None
        elif hasattr(actor, "email"):
            actor_value = getattr(actor, "email", None) or None
        else:
            actor_value = str(actor)
        actor_id = _hash_email_or_id(actor_value)
        subject_hash = _hash_email_or_id(subject)
        clean_payload = _sanitize_payload(payload_summary)
        tenant_hash = _hash_tenant_slug(tenant_slug or "")

        # v3.40.0 Agent 14 — per-tenant audit-event volume rate-limit.
        # The meta-event type is always allowed (never rate-limited
        # itself); every other event passes through the counter.
        if event_type != _AUDIT_RATE_LIMIT_META_TYPE:
            allowed, count_in_window = _rate_limit_check_and_increment(
                tenant_hash, event_type,
            )
            if not allowed:
                limit = int(getattr(
                    settings,
                    "MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR",
                    5000,
                ) or 5000)
                # Emit one meta-event per tenant per hour (deduped).
                if _rate_limit_should_emit_meta(tenant_hash):
                    meta_payload = {
                        "tenant_sha256_prefix": tenant_hash,
                        "event_type": event_type,
                        "count_in_window": int(count_in_window),
                        "limit": int(limit),
                    }
                    try:
                        with transaction.atomic():
                            meta = self.model(
                                tenant_id_hash=tenant_hash,
                                event_type=_AUDIT_RATE_LIMIT_META_TYPE,
                                actor_id=None,
                                event_subject_hash=None,
                                payload_summary=meta_payload,
                            )
                            meta.save()
                    except Exception as exc:  # pylint: disable=broad-except
                        # Don't let the meta-event write failure mask
                        # the rate-limit signal — still raise below.
                        logger.warning(
                            "migration_cloud.audit.rate_limit_meta_emit_"
                            "failed tenant_hash=%s err_type=%s",
                            tenant_hash, type(exc).__name__,
                        )
                logger.warning(
                    "migration_cloud.audit.rate_limit_triggered "
                    "tenant_hash=%s event_type=%s count=%d limit=%d",
                    tenant_hash, event_type, count_in_window, limit,
                )
                raise AuditEventRateLimitExceeded(
                    tenant_hash, event_type, count_in_window, limit,
                )

        with transaction.atomic():
            instance = self.model(
                tenant_id_hash=tenant_hash,
                event_type=event_type,
                actor_id=actor_id,
                event_subject_hash=subject_hash,
                payload_summary=clean_payload,
            )
            instance.save()
        return instance


class MigrationCloudAuditEvent(AppendOnlyModelMixin, models.Model):
    """Tamper-evident, append-only audit event for Migration Cloud."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=(
            "UUIDv4 primary key. Random so event IDs don't leak ordering "
            "or per-tenant volume."
        ),
    )
    tenant_id_hash = models.CharField(
        max_length=12,
        db_index=True,
        help_text=(
            "First 12 hex chars of sha256(tenant_slug). Auditors export by "
            "this prefix; operators correlate to the tenant via a "
            "separately-maintained map (see docs/MIGRATION_CLOUD_AUDIT_LOG.md)."
        ),
    )
    event_type = models.CharField(
        max_length=64,
        choices=MigrationCloudAuditEventType.choices,
        db_index=True,
        help_text="One of the registered audit event types.",
    )
    actor_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text=(
            "sha256(user.email)[:64] when authenticated. NULL for system "
            "events (Celery beat). NEVER the raw email."
        ),
    )
    event_subject_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text=(
            "sha256(subject_id_or_slug)[:64] of the entity the event acts on "
            "(webhook sub UUID, token id, MAA id, ...). NULL when no concrete "
            "subject."
        ),
    )
    payload_summary = models.JSONField(
        default=dict,
        help_text=(
            "Small structured summary (counts, booleans, hex prefixes). NEVER "
            "PII; NEVER signature/key/password material — enforced by "
            "_sanitize_payload at write time."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    created_at_iso = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=(
            "ISO-8601 UTC representation of created_at, populated in save() "
            "so the value is present even on raw-SQL exports."
        ),
    )
    integrity_hash = models.CharField(
        max_length=64,
        editable=False,
        help_text=(
            "SHA-256 of canonical_json({id, tenant_id_hash, event_type, "
            "actor_id, event_subject_hash, payload_summary, created_at_iso, "
            "prev_event_hash}). Chains per-tenant."
        ),
    )
    prev_event_hash = models.CharField(
        max_length=64,
        editable=False,
        help_text=(
            "Previous event's integrity_hash for the same tenant_id_hash, "
            "or 'genesis' for the first event per tenant."
        ),
    )
    # v3.39.0 Agent 2 — HMAC-SHA512 root-key signature (128 hex chars).
    # NULL = unsigned legacy (signing key wasn't configured at write
    # time); NOT NULL = verifiable via
    # ``apps.migration_cloud.services.audit_root_signing``.
    root_key_signature = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        editable=False,
        help_text=(
            "HMAC-SHA512 hex digest over the same canonical-JSON pre-image "
            "integrity_hash covers, keyed by settings."
            "MIGRATION_CLOUD_AUDIT_SIGNING_KEY when configured. NULL means "
            "the signing key wasn't set at write time (legacy event)."
        ),
    )

    objects = AuditEventManager()

    class Meta:
        verbose_name = "Migration Cloud audit event"
        verbose_name_plural = "Migration Cloud audit events"
        indexes = [
            models.Index(fields=["tenant_id_hash", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]
        # NO unique constraints — chain integrity is verified externally
        # via verify_audit_chain management command + JSONL exporter.

    def __str__(self) -> str:
        return (
            f"AuditEvent[{self.event_type}] tenant={self.tenant_id_hash} "
            f"at={self.created_at_iso or self.created_at}"
        )

    # ---------------------------------------------------------------
    # Append-only enforcement.
    # ---------------------------------------------------------------

    def save(self, *args, **kwargs):
        if self.pk is not None:
            existing = type(self).objects.filter(pk=self.pk).only("pk").first()  # tenant-isolation-allow: audit-event-self-pk-readback-pre-update-check
            if existing is not None:
                raise MigrationCloudAuditEventReadOnlyError(
                    "MigrationCloudAuditEvent rows are append-only; update refused."
                )

        # First-create path. Populate computed fields.
        if not self.id:
            self.id = uuid.uuid4()
        # ``created_at`` is set by auto_now_add on insert — for the
        # canonical pre-image we need a value NOW, so we capture
        # wall-clock and persist it as ``created_at_iso``. The DB row's
        # ``created_at`` will match within microseconds.
        now = timezone.now()
        self.created_at_iso = now.replace(microsecond=now.microsecond).isoformat()

        # Tail-lookup the previous event for this tenant. The audit
        # log is intentionally cross-tenant from the operator's POV;
        # the tail-per-tenant query is correct.
        tail = (
            type(self).objects  # tenant-isolation-allow: audit-chain-tail-lookup-per-tenant
            .filter(tenant_id_hash=self.tenant_id_hash)
            .order_by("-created_at")
            .only("integrity_hash")
            .first()
        )
        self.prev_event_hash = (
            tail.integrity_hash if tail is not None else GENESIS_SENTINEL
        )

        # Ensure payload_summary is a dict.
        if self.payload_summary is None:
            self.payload_summary = {}

        self.integrity_hash = _compute_integrity_hash(
            pk=str(self.id),
            tenant_id_hash=self.tenant_id_hash,
            event_type=self.event_type,
            actor_id=self.actor_id,
            event_subject_hash=self.event_subject_hash,
            payload_summary=self.payload_summary,
            created_at_iso=self.created_at_iso,
            prev_event_hash=self.prev_event_hash,
        )
        # v3.39.0 Agent 2 — root-key signature. Computed AFTER
        # integrity_hash so the same canonical pre-image is locked by
        # both layers. Failure modes:
        #   * key unset           → returns None; row persists unsigned.
        #   * unknown backend     → returns None; row persists unsigned.
        #   * HSM backend value   → NotImplementedError propagates (we
        #     refuse to silently degrade an HSM-policy deployment).
        #   * any other exception → log + None; never breaks the audit
        #     write hot path.
        try:
            from apps.migration_cloud.services.audit_root_signing import (
                compute_root_signature,
            )
            self.root_key_signature = compute_root_signature(self)
        except NotImplementedError:
            # HSM-reserved backend — surface to caller. Audit-event
            # writers should not silently downgrade.
            raise
        except Exception as exc:  # broad-by-design — never break hot path
            logger.warning(
                "migration_cloud.audit.root_signature.compute_failed "
                "event_id_prefix=%s err_type=%s",
                str(self.id)[:8], type(exc).__name__,
            )
            self.root_key_signature = None
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        raise MigrationCloudAuditEventReadOnlyError(
            "MigrationCloudAuditEvent rows are append-only; delete refused."
        )

    def recompute_integrity_hash(self) -> str:
        """Re-derive the integrity hash from current field values.

        Used by the verifier — does NOT modify the stored row.
        """
        return _compute_integrity_hash(
            pk=str(self.id),
            tenant_id_hash=self.tenant_id_hash,
            event_type=self.event_type,
            actor_id=self.actor_id,
            event_subject_hash=self.event_subject_hash,
            payload_summary=self.payload_summary,
            created_at_iso=self.created_at_iso,
            prev_event_hash=self.prev_event_hash,
        )

    def to_export_dict(self) -> dict:
        """Return the dict serialized to one JSONL line during export."""
        return {
            "id": str(self.id),
            "tenant_id_hash": self.tenant_id_hash,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "event_subject_hash": self.event_subject_hash,
            "payload_summary": _sanitize_payload(self.payload_summary or {}),
            "created_at_iso": self.created_at_iso,
            "integrity_hash": self.integrity_hash,
            "prev_event_hash": self.prev_event_hash,
            "root_key_signature": getattr(self, "root_key_signature", None),
        }


__all__ = [
    "MigrationCloudAuditEvent",
    "MigrationCloudAuditEventType",
    "MigrationCloudAuditEventReadOnlyError",
    "AuditEventManager",
    "AuditEventRateLimitExceeded",
    "GENESIS_SENTINEL",
    "_sanitize_payload",
    "_hash_tenant_slug",
    "_hash_email_or_id",
    "_compute_integrity_hash",
    "_canonical_json",
    "_rate_limit_check_and_increment",
    "_rate_limit_should_emit_meta",
    "_rate_limit_reset_for_tests",
    "_rate_limit_clock",
    "_rate_limit_window_seconds",
    "_AUDIT_RATE_LIMIT_META_TYPE",
]
