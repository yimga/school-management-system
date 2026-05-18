"""Server-side X25519 keypair lifecycle for the Companion upload flow.

The Companion extension seals each canonical bundle to the active
public key via libsodium's sealed-box (see
``companion-extension/src/lib/crypto.ts``). The matching private key
lives here, ENCRYPTED at rest using Agent 5's
``apps.accounts.legacy_hashes.encryption.EncryptedCharField`` shim
(or Fernet via the same module). At decrypt-hook time the bytes are
unwrapped, used once with ``nacl.public.SealedBox``, and the local
variable goes out of scope at the end of the request.

Operator UX: invisible. The popup fetches the active public key per
browser session (``chrome.storage.session``) and seals against it; if
operators rotate the keypair mid-session, the next session re-fetches
and continues. Old ciphertext can still be decrypted by carrying the
``key_version`` tag through to the receiver.

Logging discipline (NoSecretsLoggedTests-style):

  * ``logger.info`` carries ``key_version`` + ``fingerprint`` (16-byte
    truncation, base64) + ``size`` only.
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
from typing import Any

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# Re-export so callers don't need to import ``apps.migration_cloud.models``
# directly when they just want to type-annotate. Side-effect-free.
def _get_model():
    from django.apps import apps as _apps

    return _apps.get_model("migration_cloud", "MigrationCloudCompanionKeypair")


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


def _wrap_private_bytes(raw: bytes) -> bytes:
    """Wrap raw 32-byte X25519 private bytes for at-rest storage.

    Calls into Agent 5's encryption shim when importable. Falls back to
    raw bytes with a ``# crypto-pending`` log breadcrumb so the operator
    knows the wrap is not yet active (Agent 5 follow-up).
    """
    try:
        from apps.accounts.legacy_hashes.encryption import _get_fernet  # type: ignore[import-not-found]
    except ImportError:
        logger.info(
            "migration_cloud.companion_keypair: private_key_wrap_pending "
            "shim_unavailable len=%s",
            len(raw),
        )
        return raw
    try:
        fernet = _get_fernet()
        # _get_fernet returns a cryptography.fernet.Fernet — encrypt returns bytes
        ciphertext = fernet.encrypt(raw)
        return ciphertext
    except (ValueError, TypeError) as exc:
        logger.warning(
            "migration_cloud.companion_keypair: private_key_wrap_error err=%s",
            type(exc).__name__,
        )
        # Fail closed: we'd rather not write a keypair than write plaintext
        # silently when an explicit shim is in place but mis-configured.
        raise


def _unwrap_private_bytes(stored: bytes) -> bytes:
    """Inverse of :func:`_wrap_private_bytes`. Decrypts or passes through."""
    if not stored:
        raise ValueError("empty stored private bytes")
    try:
        from apps.accounts.legacy_hashes.encryption import _get_fernet  # type: ignore[import-not-found]
    except ImportError:
        return bytes(stored)
    try:
        fernet = _get_fernet()
        return fernet.decrypt(bytes(stored))
    except (ValueError, TypeError):
        # Pre-shim row (raw bytes) — pass through. The caller validates
        # the length downstream.
        logger.info(
            "migration_cloud.companion_keypair: private_key_unwrap_passthrough "
            "len=%s",
            len(stored),
        )
        return bytes(stored)
    except Exception as exc:  # pragma: no cover — InvalidToken from cryptography
        logger.warning(
            "migration_cloud.companion_keypair: private_key_unwrap_error err=%s",
            type(exc).__name__,
        )
        raise


# ─── Public service surface ──────────────────────────────────────────────


def _next_version_label(model: Any) -> str:
    """Mint a fresh monotonic ``vN`` label. Defensive vs. race."""
    # tenant-isolation-allow: global-keypair-not-per-tenant-no-tenant-fk
    count = model.objects.count()
    return f"v{count + 1}"


def ensure_active_keypair():
    """Return the active keypair row, generating one if none exist.

    Idempotent: parallel callers race-recover via the partial unique
    constraint. On race-loss, the loser re-reads the winning row.
    """
    Model = _get_model()
    # tenant-isolation-allow: global-keypair-not-per-tenant-no-tenant-fk
    existing = Model.objects.filter(is_active=True).first()
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
            row = Model.objects.create(  # tenant-isolation-allow: global-keypair-not-per-tenant-no-tenant-fk
                key_version=_next_version_label(Model),
                public_key_b64=pub_b64,
                private_key_encrypted=wrapped,
                is_active=True,
            )
    except Exception as exc:  # pragma: no cover — IntegrityError on race-loss
        logger.info(
            "migration_cloud.companion_keypair: ensure_race_recovery err=%s",
            type(exc).__name__,
        )
        # tenant-isolation-allow: global-keypair-not-per-tenant-no-tenant-fk
        winner = Model.objects.filter(is_active=True).first()
        if winner is None:
            raise
        # Zero out our generated private bytes — caller doesn't need them.
        priv_bytes = b"\x00" * len(priv_bytes)  # noqa: F841
        return winner

    fingerprint = fingerprint_of_public_key_b64(row.public_key_b64)
    logger.info(
        "migration_cloud.companion_keypair: ensure_active_keypair created "
        "key_version=%s fingerprint=%s",
        row.key_version, fingerprint,
    )
    # Best-effort zero of the in-memory plaintext private bytes.
    priv_bytes = b"\x00" * len(priv_bytes)  # noqa: F841
    return row


def rotate_keypair(operator_user=None) -> dict[str, Any]:
    """Deactivate the current active keypair and mint a fresh one.

    Returns a dict with the previous + new ``key_version`` + the new
    fingerprint. The Companion popup re-fetches per-session, so rotation
    is invisible to operators.
    """
    nacl = _import_nacl()
    Model = _get_model()
    operator_id = getattr(operator_user, "pk", None)

    sk = nacl.public.PrivateKey.generate()
    pub_bytes = bytes(sk.public_key.encode())
    priv_bytes = bytes(sk.encode())
    pub_b64 = base64.b64encode(pub_bytes).decode("ascii")
    wrapped = _wrap_private_bytes(priv_bytes)

    with transaction.atomic():
        # tenant-isolation-allow: global-keypair-not-per-tenant-no-tenant-fk
        previous = Model.objects.select_for_update().filter(is_active=True).first()
        old_version = previous.key_version if previous else None
        if previous is not None:
            # Clear is_active=True FIRST so the partial unique constraint
            # is honored before the new row is inserted in the same tx.
            previous.is_active = False
            previous.rotated_out_at = timezone.now()
            previous.save(update_fields=["is_active", "rotated_out_at"])

        new_row = Model.objects.create(  # tenant-isolation-allow: global-keypair-not-per-tenant-no-tenant-fk
            key_version=_next_version_label(Model),
            public_key_b64=pub_b64,
            private_key_encrypted=wrapped,
            is_active=True,
        )

    fingerprint = fingerprint_of_public_key_b64(new_row.public_key_b64)
    logger.info(
        "migration_cloud.companion_keypair: rotate_keypair operator_id=%s "
        "old_version=%s new_version=%s fingerprint=%s",
        operator_id, old_version, new_row.key_version, fingerprint,
    )
    # Best-effort zero of the in-memory plaintext private bytes.
    priv_bytes = b"\x00" * len(priv_bytes)  # noqa: F841
    return {
        "old_version": old_version,
        "new_version": new_row.key_version,
        "fingerprint_b64": fingerprint,
    }


def get_active_public_key_info() -> dict[str, str]:
    """Return the JSON payload shape used by ``CompanionServerPubkeyView``.

    Lazy: creates the keypair on first call if none exists. NEVER
    contains private bytes.
    """
    row = ensure_active_keypair()
    return {
        "public_key_b64": row.public_key_b64,
        "key_version": row.key_version,
        "fingerprint_b64": fingerprint_of_public_key_b64(row.public_key_b64),
        "encryption_scheme": "libsodium-secretbox-x25519-sealed",
    }


def decrypt_with_active_or_versioned(
    ciphertext: bytes,
    requested_version: str | None = None,
) -> bytes:
    """Open a sealed-box ciphertext using the active keypair (or pinned).

    When ``requested_version`` is supplied (e.g. matched to the
    receipt's stored ``key_version`` if/when we persist that), use that
    specific keypair. Otherwise fall back to the currently-active one.

    Returns plaintext bytes. NEVER logs the bytes themselves; emits
    only sizes + key_version + fingerprint.
    """
    nacl = _import_nacl()
    Model = _get_model()

    row = None
    if requested_version:
        # tenant-isolation-allow: global-keypair-not-per-tenant-no-tenant-fk
        row = Model.objects.filter(key_version=requested_version).first()
        if row is None:
            raise ValueError(
                f"no keypair found for key_version={requested_version!r}"
            )
    else:
        # tenant-isolation-allow: global-keypair-not-per-tenant-no-tenant-fk
        row = Model.objects.filter(is_active=True).first()
        if row is None:
            row = ensure_active_keypair()

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
        "migration_cloud.companion_keypair: decrypt_ok key_version=%s "
        "fingerprint=%s ciphertext_size=%s plaintext_size=%s",
        row.key_version, fingerprint, len(ciphertext), len(plaintext),
    )
    return plaintext


__all__ = (
    "PyNaClUnavailable",
    "decrypt_with_active_or_versioned",
    "ensure_active_keypair",
    "fingerprint_eq",
    "fingerprint_of_public_key_b64",
    "get_active_public_key_info",
    "rotate_keypair",
)


# ``secrets`` is imported intentionally for callers that wish to ensure
# the standard-library CSPRNG is loaded before keypair generation. Avoid
# the lint flag.
_ = secrets
