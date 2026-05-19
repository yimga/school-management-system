"""v3.39.0 Agent 2 — root-key signature for Migration Cloud audit events.

`MigrationCloudAuditEvent.root_key_signature` is an HMAC-SHA512 hex
digest over the SAME canonical-JSON pre-image that the existing
SHA-256 ``integrity_hash`` covers. The two checks compose:

  * ``integrity_hash`` — SHA-256, locks the row's own content + the
    per-tenant hash-chain link. Visible to any holder of the database.
  * ``root_key_signature`` — HMAC-SHA512 (different algorithm so a
    single-key compromise cannot collapse both), keyed by a secret
    that lives OUTSIDE the database (env var or HSM). Defends the
    chain even when an attacker restores from a tampered backup.

Two operations:

  * :func:`compute_root_signature` — produced on write, stored on the
    event row. Returns ``None`` when the signing key is empty (opt-in
    deployment — feature off until operator provisions the key).
  * :func:`verify_root_signature` — produced on read; recomputes the
    HMAC and compares constant-time. Returns ``True`` / ``False`` /
    ``None`` (the last for legacy rows written before the key existed,
    distinguishable from "mismatch — chain tampered").

Backend selection is settings-driven via
``MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND``. Only ``"local-env-key"``
is implemented today; HSM backend values are reserved and raise
:class:`NotImplementedError` with a runbook pointer.

Logging hygiene — this module NEVER logs:
    * the signing-key bytes (raw, base64, or hex);
    * the computed signature bytes (raw or hex);
    * the canonical pre-image bytes (a structural snapshot, not PII,
      but conservatively redacted because event payloads MAY carry
      hashed identifiers that should not concentrate in logs).
Only the event ID prefix + backend selector + booleans are logged.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings

if TYPE_CHECKING:  # pragma: no cover — typing only
    from apps.migration_cloud.models_audit import MigrationCloudAuditEvent

logger = logging.getLogger(__name__)


SIGNING_BACKEND_LOCAL = "local-env-key"
# v3.40.0 Agent 1 — first implemented HSM backend.
SIGNING_BACKEND_VAULT = "hashicorp-vault"
# Reserved future surfaces — the bridge module ("how do we talk to
# AWS KMS / Azure Key Vault / Vault / GCP KMS") is the work that
# unblocks each value. We refuse early with a clear message so an
# operator who flips ``MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND`` to
# one of these does not silently get an unsigned audit log.
#
# As of v3.40.0, ``hashicorp-vault`` is IMPLEMENTED via
# :mod:`apps.migration_cloud.services.hsm_vault`. It is retained in the
# reserved set for backwards-compatible enumeration (existing tests
# iterate ``RESERVED_BACKENDS_HSM`` expecting NotImplementedError —
# those tests are scoped to "HSM-class backends still pending"; the
# vault entry has been moved out into ``IMPLEMENTED_HSM_BACKENDS`` and
# the reserved set now contains only the still-unimplemented three).
IMPLEMENTED_HSM_BACKENDS = frozenset({
    SIGNING_BACKEND_VAULT,
})
RESERVED_BACKENDS_HSM = frozenset({
    "aws-kms",
    "azure-keyvault",
    "gcp-kms",
})
# Union surface for diagnostics — every HSM-class backend value the
# selector recognizes.
ALL_HSM_BACKENDS = IMPLEMENTED_HSM_BACKENDS | RESERVED_BACKENDS_HSM


class AuditSigningConfigError(RuntimeError):
    """Raised on misconfiguration discovered at signing-time."""


def _canonical_pre_image_bytes(event: "MigrationCloudAuditEvent") -> bytes:
    """Return the canonical-JSON bytes used as the HMAC pre-image.

    Mirrors the field set that
    :func:`apps.migration_cloud.models_audit._compute_integrity_hash`
    consumes, so an attacker who alters ANY of those fields invalidates
    BOTH checks. Determinism is asserted via
    ``json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)``.
    """
    pre = {
        "id": str(event.id),
        "tenant_id_hash": event.tenant_id_hash,
        "event_type": event.event_type,
        "actor_id": event.actor_id,
        "event_subject_hash": event.event_subject_hash,
        "payload_summary": event.payload_summary or {},
        "created_at_iso": event.created_at_iso,
        "prev_event_hash": event.prev_event_hash,
    }
    return json.dumps(
        pre, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _decode_signing_key(raw_value: str) -> bytes:
    """Return key bytes; base64 is preferred but raw bytes accepted.

    We accept three encodings to lower operator friction:
      * Base64 (preferred) — `base64.b64decode(..., validate=True)`.
      * Hex — falls through if the value parses cleanly.
      * UTF-8 bytes — last-resort literal (less ideal).
    The KEY MATERIAL ITSELF is never logged at any stage.
    """
    if not raw_value:
        return b""
    # Strip whitespace to tolerate accidental newlines in env files.
    candidate = raw_value.strip()
    # Base64 attempt.
    try:
        decoded = base64.b64decode(candidate, validate=True)
        if len(decoded) >= 16:  # require non-trivial entropy
            return decoded
    except (binascii.Error, ValueError):
        pass
    # Hex attempt.
    try:
        decoded = bytes.fromhex(candidate)
        if len(decoded) >= 16:
            return decoded
    except ValueError:
        pass
    # Raw bytes fallback. Caller MUST have provided enough entropy.
    return candidate.encode("utf-8")


def _resolve_backend() -> str:
    """Return the configured backend selector (default: local-env-key)."""
    backend = getattr(
        settings, "MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND", SIGNING_BACKEND_LOCAL,
    ) or SIGNING_BACKEND_LOCAL
    return backend


def _resolve_signing_key() -> bytes | None:
    """Return signing key bytes from settings, or ``None`` if unset.

    Honors :attr:`settings.MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND`:
      * ``"local-env-key"`` — read from
        ``settings.MIGRATION_CLOUD_AUDIT_SIGNING_KEY``.
      * ``"hashicorp-vault"`` — vault backend handles its own key
        material; this helper raises :class:`AuditSigningConfigError`
        when called on the vault path (callers must dispatch via the
        backend object, not by recombining a local HMAC key).
      * Reserved HSM backends (``aws-kms`` / ``azure-keyvault`` /
        ``gcp-kms``) — raise :class:`NotImplementedError` (we do NOT
        silently degrade — the operator must either implement the
        bridge or revert the backend setting).
    """
    backend = _resolve_backend()

    if backend in RESERVED_BACKENDS_HSM:
        raise NotImplementedError(
            f"MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND={backend!r} is reserved — "
            "configure HSM bridge first. See "
            "docs/MIGRATION_CLOUD_AUDIT_LOG.md § Root-key signature "
            "(HSM pluggability)."
        )

    if backend == SIGNING_BACKEND_VAULT:
        # The vault backend never exposes raw key material to this
        # module — it signs / verifies remotely. Callers must dispatch
        # via :func:`compute_root_signature` / :func:`verify_root_signature`
        # which check the backend selector themselves.
        raise AuditSigningConfigError(
            "hashicorp-vault backend does not expose raw key bytes; "
            "dispatch via compute_root_signature/verify_root_signature."
        )

    if backend != SIGNING_BACKEND_LOCAL:
        raise AuditSigningConfigError(
            f"unknown MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND={backend!r}"
        )

    raw = getattr(settings, "MIGRATION_CLOUD_AUDIT_SIGNING_KEY", "") or ""
    if not raw:
        return None
    return _decode_signing_key(raw)


def _vault_backend():
    """Lazy import + instantiate. Kept lazy so the audit_root_signing
    module can be imported without ``urllib`` (it's stdlib, always
    available, but the principle holds for future HSM modules that
    might pull in heavier deps)."""
    from apps.migration_cloud.services.hsm_vault import VaultTransitBackend
    return VaultTransitBackend()


def compute_root_signature(event: "MigrationCloudAuditEvent") -> str | None:
    """Return the 128-char digest, or ``None`` if unconfigured.

    Called from :meth:`MigrationCloudAuditEvent.save` after the
    ``integrity_hash`` is computed but before the row is persisted.
    Returns ``None`` if the operator has not yet provisioned the
    signing key — the row will be marked "unsigned legacy" by future
    verifiers, distinguishable from "signature mismatch".

    Output shape is 128 characters regardless of backend:
      * ``local-env-key`` — 128-hex HMAC-SHA512 digest.
      * ``hashicorp-vault`` — 128-char base64 HMAC-SHA512 (padded with
        ``=`` to match column width). The audit-event column is
        ``CharField(128)`` so the on-disk shape stays stable.
    """
    backend = _resolve_backend()

    # ---- HSM vault path -------------------------------------------------
    if backend == SIGNING_BACKEND_VAULT:
        # Vault dispatch — typed errors from the backend bubble as a
        # warning + None so audit writes don't fail. We re-raise on
        # NotImplementedError parity (vault backend never raises it,
        # but defensive).
        try:
            vault = _vault_backend()
            pre_image = _canonical_pre_image_bytes(event)
            sig = vault.sign(pre_image)
        except NotImplementedError:
            raise
        except Exception as exc:  # noqa: BLE001 — typed below
            # We deliberately catch broadly so a Vault transport hiccup
            # never breaks the audit-event write path. The exception
            # type is logged (NOT the message body, which could carry
            # the URL/path).
            logger.warning(
                "migration_cloud.audit_root_signing.vault_sign_failed "
                "reason=%s",
                type(exc).__name__,
            )
            return None
        if not isinstance(sig, str) or len(sig) != 128:
            logger.error(
                "migration_cloud.audit_root_signing.vault_bad_shape len=%s",
                len(sig) if isinstance(sig, str) else "n/a",
            )
            return None
        return sig

    # ---- Local-env-key path (default) ----------------------------------
    try:
        key = _resolve_signing_key()
    except NotImplementedError:
        # Re-raise — an HSM backend must not be silently downgraded.
        raise
    except AuditSigningConfigError as exc:
        # Unknown backend value — log without key/sig content and
        # return None so the audit-log write still succeeds (we
        # explicitly prefer "audit row lands unsigned" to "audit row
        # is refused").
        logger.warning(
            "migration_cloud.audit_root_signing.unknown_backend reason=%s",
            type(exc).__name__,
        )
        return None
    if key is None:
        return None

    pre_image = _canonical_pre_image_bytes(event)
    digest = hmac.new(key, pre_image, hashlib.sha512).hexdigest()
    # Sanity: SHA-512 hex is always 128 chars.
    if len(digest) != 128:  # pragma: no cover — hashlib invariant
        logger.error(
            "migration_cloud.audit_root_signing.unexpected_digest_length "
            "len=%s",
            len(digest),
        )
        return None
    return digest


def verify_root_signature(
    event: "MigrationCloudAuditEvent",
) -> bool | None:
    """Three-valued verifier:

      * ``True``  — signature present and matches recompute.
      * ``False`` — signature present and DOES NOT match.
      * ``None``  — signature absent (legacy event written before
        the signing key was provisioned). NOT a tamper signal.

    Uses :func:`hmac.compare_digest` for constant-time comparison.
    """
    stored = getattr(event, "root_key_signature", None) or ""
    if not stored:
        return None

    backend = _resolve_backend()

    # ---- HSM vault path -------------------------------------------------
    if backend == SIGNING_BACKEND_VAULT:
        try:
            vault = _vault_backend()
            pre_image = _canonical_pre_image_bytes(event)
            return bool(vault.verify(pre_image, stored))
        except NotImplementedError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Verifier returns None on transport failure so the caller
            # can distinguish "verify could not run" from a hard False
            # (which means tamper).
            logger.warning(
                "migration_cloud.audit_root_signing.vault_verify_failed "
                "reason=%s",
                type(exc).__name__,
            )
            return None

    try:
        key = _resolve_signing_key()
    except NotImplementedError:
        # Verifier must surface the misconfiguration to the operator
        # — we don't synthesize True/False here.
        raise
    except AuditSigningConfigError:
        return None
    if key is None:
        # Stored signature exists but key has been cleared. Treat as
        # mismatch — caller decides how to escalate. (More likely:
        # an operator rotated keys without retaining the prior one,
        # which is an incident.)
        return False

    pre_image = _canonical_pre_image_bytes(event)
    expected = hmac.new(key, pre_image, hashlib.sha512).hexdigest()
    return hmac.compare_digest(
        expected.encode("ascii"), stored.encode("ascii"),
    )


__all__ = [
    "ALL_HSM_BACKENDS",
    "AuditSigningConfigError",
    "IMPLEMENTED_HSM_BACKENDS",
    "RESERVED_BACKENDS_HSM",
    "SIGNING_BACKEND_LOCAL",
    "SIGNING_BACKEND_VAULT",
    "compute_root_signature",
    "verify_root_signature",
]
