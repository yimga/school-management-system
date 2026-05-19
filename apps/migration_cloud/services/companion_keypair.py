"""Server-side X25519 keypair lifecycle for the Companion upload flow.

The Companion extension seals each canonical bundle to the active
public key via libsodium's sealed-box (see
``companion-extension/src/lib/crypto.ts``). The matching private key
lives here, ENCRYPTED at rest using the
``apps.accounts.legacy_hashes.encryption.EncryptedBinaryField``
descriptor (Fernet wrap). At decrypt-hook time the bytes are
unwrapped, used once with ``nacl.public.SealedBox``, and the local
variable goes out of scope at the end of the request.

v3.34.0 — keypairs are now PER-TENANT. Every public function on this
module accepts ``tenant`` as its first positional argument and scopes
its queries to that tenant. A single-tenant key leak no longer blasts
radius across the platform.

Operator UX: invisible. The popup fetches the active public key per
browser session (``chrome.storage.session``) and seals against it; if
operators rotate the keypair mid-session, the next session re-fetches
and continues. Old ciphertext can still be decrypted by carrying the
``key_version`` tag through to the receiver.

Logging discipline (NoSecretsLoggedTests-style):

  * ``logger.info`` carries ``tenant_pk`` + ``key_version`` +
    ``fingerprint`` (16-byte truncation, base64) + ``size`` only.
  * ``private_key_encrypted`` bytes never reach the logger.
  * The fingerprint comparison helper (:func:`fingerprint_eq`) uses
    :func:`hmac.compare_digest` for constant-time semantics.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DecryptResult:
    """Return value for :func:`decrypt_with_active_or_versioned`.

    Carries both the recovered plaintext bytes AND the keypair version
    that opened them. Receivers persist ``key_version`` on the receipt
    so an auditor can later answer "which server key half opened R?"
    without replaying the keypair rotation history.

    Defensive: callers MUST treat ``plaintext`` as sensitive — zeroize
    when scope ends. Callers MUST NOT log either field.
    """

    plaintext: bytes
    key_version: str
    fingerprint_b64: str


# Re-export so callers don't need to import ``apps.migration_cloud.models``
# directly when they just want to type-annotate. Side-effect-free.
def _get_model():
    from django.apps import apps as _apps

    return _apps.get_model("migration_cloud", "MigrationCloudCompanionKeypair")


def _tenant_pk(tenant) -> Any:
    """Return the FK reference (pk) for a tenant arg, accepting model OR pk.

    Callers may pass an instance OR a primary key directly. Centralizing
    the unwrap keeps the queryset filters uniform across functions.
    """
    if tenant is None:
        raise ValueError("tenant is required (v3.34.0 per-tenant scoping)")
    return getattr(tenant, "pk", tenant)


# ─── Crypto helpers (PyNaCl required) ────────────────────────────────────


class PyNaClUnavailable(RuntimeError):
    """Raised when ``nacl`` cannot be imported. The view layer maps to 501."""


def _import_nacl():
    try:
        import nacl.public  # type: ignore[import-not-found]
        return nacl
    except ImportError as exc:
        raise PyNaClUnavailable(
            "PyNaCl required for companion keypair operations"
        ) from exc


def fingerprint_of_public_key_b64(public_key_b64: str) -> str:
    """Return the base64-encoded first 16 bytes of sha256(public_key_b64).

    Truncation prevents accidental full-hash disclosure to loggers; 16
    bytes (128 bits) is collision-resistant well beyond a deployment's
    keypair count.
    """
    digest = hashlib.sha256(public_key_b64.encode("ascii")).digest()
    return base64.b64encode(digest[:16]).decode("ascii")


def fingerprint_eq(a: str, b: str) -> bool:
    """Constant-time fingerprint equality. Defends against timing oracles."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ─── Encryption wrap / unwrap for the private bytes ──────────────────────
#
# The model field is
# ``apps.accounts.legacy_hashes.encryption.EncryptedBinaryField`` (a
# Fernet-wrapping descriptor). Writes encrypt on the way out; reads
# decrypt on the way in. The helpers below are no-op pass-throughs kept
# only so legacy callers that imported them keep working. New code
# should assign / read ``private_key_encrypted`` directly.


def _wrap_private_bytes(raw: bytes) -> bytes:
    """Pass-through identity. Model field handles encryption.

    Kept for legacy callers. The descriptor wraps the bytes on save;
    returning ``raw`` here means the bytes round-trip cleanly through
    the wrap. Empty input is accepted (caller-side guard).
    """
    return raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)


def _unwrap_private_bytes(stored: bytes) -> bytes:
    """Pass-through identity. Model field handles decryption.

    The :class:`EncryptedBinaryField` descriptor's ``from_db_value`` has
    already decrypted ``stored`` by the time it lands on the row
    instance. We accept ``memoryview`` and bytearray for driver
    portability and normalize to ``bytes``.
    """
    if not stored:
        raise ValueError("empty stored private bytes")
    if isinstance(stored, memoryview):
        return stored.tobytes()
    if isinstance(stored, bytearray):
        return bytes(stored)
    return bytes(stored)


# ─── Public service surface ──────────────────────────────────────────────


def _next_version_label(model: Any, tenant_pk: Any) -> str:
    """Mint a fresh per-tenant monotonic ``vN`` label. Defensive vs. race."""
    # tenant-isolation-allow: keypair-version-label-scoped-per-tenant-fk
    count = model.objects.filter(tenant_id=tenant_pk).count()
    return f"v{count + 1}"


def ensure_active_keypair(tenant):
    """Return the active keypair row for ``tenant``, minting on first use.

    Idempotent within a tenant: parallel callers race-recover via the
    per-tenant partial unique constraint. On race-loss, the loser
    re-reads the winning row.

    ``tenant`` may be a ``schools.School`` instance OR its pk.
    """
    Model = _get_model()
    tenant_pk = _tenant_pk(tenant)
    # tenant-isolation-allow: keypair-lookup-scoped-per-tenant-fk-active-true
    existing = Model.objects.filter(tenant_id=tenant_pk, is_active=True).first()
    if existing is not None:
        return existing

    nacl = _import_nacl()
    sk = nacl.public.PrivateKey.generate()
    pub_bytes = bytes(sk.public_key.encode())
    priv_bytes = bytes(sk.encode())
    pub_b64 = base64.b64encode(pub_bytes).decode("ascii")
    wrapped = _wrap_private_bytes(priv_bytes)

    try:
        with transaction.atomic():
            row = Model.objects.create(  # tenant-isolation-allow: keypair-create-scoped-per-tenant-fk-on-mint
                tenant_id=tenant_pk,
                key_version=_next_version_label(Model, tenant_pk),
                public_key_b64=pub_b64,
                private_key_encrypted=wrapped,
                is_active=True,
            )
    except Exception as exc:  # pragma: no cover — IntegrityError on race-loss
        logger.info(
            "migration_cloud.companion_keypair: ensure_race_recovery "
            "tenant_pk=%s err=%s",
            tenant_pk, type(exc).__name__,
        )
        # tenant-isolation-allow: keypair-race-recovery-scoped-per-tenant-fk
        winner = Model.objects.filter(
            tenant_id=tenant_pk, is_active=True
        ).first()
        if winner is None:
            raise
        # Zero out our generated private bytes — caller doesn't need them.
        priv_bytes = b"\x00" * len(priv_bytes)  # noqa: F841
        return winner

    fingerprint = fingerprint_of_public_key_b64(row.public_key_b64)
    logger.info(
        "migration_cloud.companion_keypair: ensure_active_keypair created "
        "tenant_pk=%s key_version=%s fingerprint=%s",
        tenant_pk, row.key_version, fingerprint,
    )
    # Best-effort zero of the in-memory plaintext private bytes.
    priv_bytes = b"\x00" * len(priv_bytes)  # noqa: F841
    return row


def rotate_active_keypair(tenant, operator_user=None) -> dict[str, Any]:
    """Deactivate the tenant's current active keypair and mint a fresh one.

    Returns a dict with the previous + new ``key_version`` + the new
    fingerprint. The Companion popup re-fetches per-session, so rotation
    is invisible to operators.
    """
    nacl = _import_nacl()
    Model = _get_model()
    tenant_pk = _tenant_pk(tenant)
    operator_id = getattr(operator_user, "pk", None)

    sk = nacl.public.PrivateKey.generate()
    pub_bytes = bytes(sk.public_key.encode())
    priv_bytes = bytes(sk.encode())
    pub_b64 = base64.b64encode(pub_bytes).decode("ascii")
    wrapped = _wrap_private_bytes(priv_bytes)

    with transaction.atomic():
        previous = (
            Model.objects  # tenant-isolation-allow: keypair-rotation-select-prev-scoped-per-tenant-fk
            .select_for_update()
            .filter(tenant_id=tenant_pk, is_active=True)
            .first()
        )
        old_version = previous.key_version if previous else None
        if previous is not None:
            # Clear is_active=True FIRST so the partial unique constraint
            # is honored before the new row is inserted in the same tx.
            previous.is_active = False
            previous.rotated_out_at = timezone.now()
            previous.save(update_fields=["is_active", "rotated_out_at"])

        new_row = Model.objects.create(  # tenant-isolation-allow: keypair-create-after-rotation-scoped-per-tenant-fk
            tenant_id=tenant_pk,
            key_version=_next_version_label(Model, tenant_pk),
            public_key_b64=pub_b64,
            private_key_encrypted=wrapped,
            is_active=True,
        )

    fingerprint = fingerprint_of_public_key_b64(new_row.public_key_b64)
    logger.info(
        "migration_cloud.companion_keypair: rotate_active_keypair "
        "tenant_pk=%s operator_id=%s old_version=%s new_version=%s "
        "fingerprint=%s",
        tenant_pk, operator_id, old_version, new_row.key_version, fingerprint,
    )
    # Best-effort zero of the in-memory plaintext private bytes.
    priv_bytes = b"\x00" * len(priv_bytes)  # noqa: F841
    return {
        "tenant_pk": str(tenant_pk),
        "old_version": old_version,
        "new_version": new_row.key_version,
        "fingerprint_b64": fingerprint,
    }


# v3.32-era alias preserved for back-compat callers; new code SHOULD
# use ``rotate_active_keypair``. The wrapper enforces the per-tenant
# arg signature.
def rotate_keypair(tenant, operator_user=None) -> dict[str, Any]:
    """Back-compat alias for :func:`rotate_active_keypair`.

    v3.32 callers wrote ``rotate_keypair(operator_user=u)``; v3.34
    requires a tenant first arg, so any unmigrated callsite raises a
    clear ``TypeError`` at the call site rather than silently rotating
    the wrong tenant.
    """
    return rotate_active_keypair(tenant, operator_user=operator_user)


def get_active_public_key_info(tenant) -> dict[str, str]:
    """Return the JSON payload shape used by ``companion_server_pubkey_view``.

    Lazy: creates the keypair on first call if none exists for the
    tenant. NEVER contains private bytes.
    """
    row = ensure_active_keypair(tenant)
    return {
        "public_key_b64": row.public_key_b64,
        "key_version": row.key_version,
        "fingerprint_b64": fingerprint_of_public_key_b64(row.public_key_b64),
        "encryption_scheme": "libsodium-secretbox-x25519-sealed",
    }


def decrypt_with_active_or_versioned(
    tenant,
    ciphertext: bytes,
    key_version: str | None = None,
) -> DecryptResult:
    """Open a sealed-box ciphertext using the tenant's keypair.

    When ``key_version`` is supplied (e.g. matched to the receipt's
    stored ``key_version``), use that specific tenant keypair.
    Otherwise fall back to the tenant's currently-active one.

    A tenant CANNOT open a ciphertext sealed for another tenant: the
    queryset filter scopes by ``tenant_id``, so a mismatched key half
    will surface as a ``CryptoError`` from libsodium rather than a
    cross-tenant decrypt. Tests assert this invariant.

    Returns a :class:`DecryptResult` carrying both the plaintext bytes
    AND the keypair version that opened them, so the receiver can
    persist the version on the ``CompanionUploadReceipt`` row. NEVER
    logs the bytes themselves; emits only sizes + tenant_pk +
    key_version + fingerprint.
    """
    nacl = _import_nacl()
    Model = _get_model()
    tenant_pk = _tenant_pk(tenant)

    row = None
    if key_version:
        # tenant-isolation-allow: keypair-decrypt-pinned-version-scoped-per-tenant-fk
        row = Model.objects.filter(
            tenant_id=tenant_pk, key_version=key_version
        ).first()
        if row is None:
            raise ValueError(
                f"no keypair found for tenant_pk={tenant_pk!s} "
                f"key_version={key_version!r}"
            )
    else:
        # tenant-isolation-allow: keypair-decrypt-active-scoped-per-tenant-fk
        row = Model.objects.filter(
            tenant_id=tenant_pk, is_active=True
        ).first()
        if row is None:
            row = ensure_active_keypair(tenant)

    raw_priv = _unwrap_private_bytes(bytes(row.private_key_encrypted))
    # Defensive: a malformed at-rest row could hand us back ciphertext
    # rather than 32-byte private material. The PrivateKey constructor
    # surfaces a clear ValueError downstream.
    if len(raw_priv) != 32:
        raise ValueError(
            "stored private key has unexpected length "
            f"(expected 32, got {len(raw_priv)})"
        )

    try:
        priv_key = nacl.public.PrivateKey(raw_priv)
        sealed_box = nacl.public.SealedBox(priv_key)
        plaintext = sealed_box.decrypt(ciphertext)
    finally:
        # Best-effort zero of the unwrapped private bytes before scope exit.
        raw_priv = b"\x00" * len(raw_priv)  # noqa: F841

    fingerprint = fingerprint_of_public_key_b64(row.public_key_b64)
    logger.info(
        "migration_cloud.companion_keypair: decrypt_ok tenant_pk=%s "
        "key_version=%s fingerprint=%s ciphertext_size=%s plaintext_size=%s",
        tenant_pk, row.key_version, fingerprint,
        len(ciphertext), len(plaintext),
    )
    return DecryptResult(
        plaintext=plaintext,
        key_version=row.key_version,
        fingerprint_b64=fingerprint,
    )


__all__ = (
    "DecryptResult",
    "PyNaClUnavailable",
    "decrypt_with_active_or_versioned",
    "ensure_active_keypair",
    "fingerprint_eq",
    "fingerprint_of_public_key_b64",
    "get_active_public_key_info",
    "rotate_active_keypair",
    "rotate_keypair",
)


# ``secrets`` is imported intentionally for callers that wish to ensure
# the standard-library CSPRNG is loaded before keypair generation. Avoid
# the lint flag.
_ = secrets
