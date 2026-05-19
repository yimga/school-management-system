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
import uuid
from typing import Any

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
    "GENESIS_SENTINEL",
    "_sanitize_payload",
    "_hash_tenant_slug",
    "_hash_email_or_id",
    "_compute_integrity_hash",
    "_canonical_json",
]
