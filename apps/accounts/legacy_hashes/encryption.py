"""Encryption layer for legacy hash storage at rest.

The foreign-vendor password hash (``User.legacy_password_hash``) is
credential-equivalent until the user logs in for the first time and we
re-hash to Argon2. Storing it as plaintext in the DB means an offline
DB dump leaks every legacy password to brute-force attacks at the
foreign vendor's iteration count. We instead store it encrypted with
Fernet (AES-128-CBC + HMAC-SHA256), using a key sourced from the
``DJANGO_CRYPTOGRAPHY_KEY`` environment variable (or a key derived from
``SECRET_KEY`` as a development fallback).

Two backends are available, selected at import time:

1. **Upstream django-cryptography 1.x.** When django-cryptography can be
   imported on the running Django version, we use
   :func:`django_cryptography.fields.encrypt` directly so the field
   migration is one line. The decryption is transparent at read time —
   callers see plaintext.
2. **Internal Fernet wrapper.** django-cryptography 1.1 imports
   ``django.utils.baseconv`` which was removed in Django 5.0; until the
   upstream ships Django-5 support (a 1.2 release or community fork),
   we use a self-contained shim built on the ``cryptography`` package
   (already required transitively). The shim implements the same
   "transparent at read time, ciphertext at write time" contract via
   custom ``CharField`` / ``JSONField`` subclasses.

Either way, the User model imports :func:`encrypt_charfield` /
:func:`encrypt_jsonfield` (NOT the raw Django field classes) for the
three legacy_* fields. Migration 0033 wraps the existing AddField
descriptors with these helpers via AlterField.

Security invariants:

* The encryption key is NEVER logged. Logger sites that touch this
  module emit only counts + statuses.
* Plaintext is held in memory only during the verify path
  (:mod:`apps.accounts.auth_backends_legacy`) and is cleared the same
  instant the user is upgraded to a native Argon2 password.
* Falling back to ``SECRET_KEY``-derived material is a documented
  development convenience. Production deployments MUST set
  ``DJANGO_CRYPTOGRAPHY_KEY`` to a freshly generated Fernet key —
  rotation procedure documented in
  ``docs/SECURITY_KEYS.md`` (referenced from the v3.29 docket entry).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Any

from django.db import models

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def _resolve_fernet_key() -> bytes:
    """Resolve the *primary* (newest) Fernet key bytes.

    Returns 32 url-safe base64-encoded bytes (the format Fernet expects).

    Resolution order:

    1. ``settings.DJANGO_CRYPTOGRAPHY_KEYS`` (list, newest-first) — if
       set, returns the first entry. This is the v3.33.0 rotation path.
    2. ``DJANGO_CRYPTOGRAPHY_KEY`` env var (singular, legacy). If set,
       it must be a valid url-safe-base64 Fernet key (44 chars, 32 raw
       bytes).
    3. ``SECRET_KEY`` from Django settings, SHA-256 hashed and
       url-safe-base64 encoded. Development convenience only.
    """
    # v3.33.0 — MultiFernet rotation path. Newest key first.
    keys = _resolve_fernet_key_list()
    if keys:
        return keys[0]

    # Dev/test fallback: derive deterministically from SECRET_KEY.
    try:
        from django.conf import settings  # local import: side-effect-free at module load
        secret = getattr(settings, "SECRET_KEY", "") or "dev-fallback"
    except Exception:  # pragma: no cover - settings should always import
        secret = "dev-fallback"
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    derived = base64.urlsafe_b64encode(digest)
    logger.info(
        "django_cryptography_key_derived_from_secret_key",
        extra={"source": "SECRET_KEY", "production_safe": False},
    )
    return derived


def _resolve_fernet_key_list() -> list[bytes]:
    """Resolve the ordered list of Fernet keys (newest-first).

    v3.33.0 MultiFernet rotation support. Resolution order:

    1. ``settings.DJANGO_CRYPTOGRAPHY_KEYS`` — Python list of
       url-safe-base64 strings. Newest-first. Used by the rotation
       code path.
    2. ``DJANGO_CRYPTOGRAPHY_KEY`` env var (singular, legacy) — one key.
    3. Empty list — caller falls through to SECRET_KEY-derived path.

    NEVER logs the key bytes themselves — only counts + a length-check
    side-channel. A length mismatch is a configuration error worth
    surfacing; the key itself is not emitted.
    """
    out: list[bytes] = []

    # Highest priority: list-typed setting for rotation.
    try:
        from django.conf import settings  # local import
        list_setting = getattr(settings, "DJANGO_CRYPTOGRAPHY_KEYS", None)
    except Exception:  # pragma: no cover - settings should always import
        list_setting = None
    if list_setting:
        if isinstance(list_setting, (list, tuple)):
            for entry in list_setting:
                if not entry:
                    continue
                if isinstance(entry, bytes):
                    out.append(entry)
                elif isinstance(entry, str):
                    s = entry.strip()
                    if s:
                        if len(s) != 44:
                            logger.warning(
                                "django_cryptography_keys_entry_unexpected_length",
                                extra={"len": len(s), "expected": 44, "position": len(out)},
                            )
                        out.append(s.encode("ascii"))
        if out:
            return out

    # Singular env var (legacy single-key deployments).
    env_key = (os.environ.get("DJANGO_CRYPTOGRAPHY_KEY") or "").strip()
    if env_key:
        if len(env_key) != 44:
            logger.warning(
                "django_cryptography_key_unexpected_length",
                extra={"len": len(env_key), "expected": 44},
            )
        out.append(env_key.encode("ascii"))
    return out


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

_USE_UPSTREAM = False
try:  # pragma: no cover - branch coverage depends on installed pkg + Django version
    from django_cryptography.fields import encrypt as _upstream_encrypt  # type: ignore[import-not-found]
    _USE_UPSTREAM = True
except ImportError:
    _USE_UPSTREAM = False
except Exception:  # noqa: BLE001 - we MUST tolerate any startup error from the optional dep
    # django-cryptography 1.1 raises ImportError on Django 5.x because
    # django.utils.baseconv was removed. Any unexpected error here
    # should NOT take down the auth path; the internal shim still works.
    logger.info(
        "django_cryptography_upstream_unavailable",
        extra={"fallback": "internal_fernet_wrapper"},
    )
    _USE_UPSTREAM = False


def _get_fernet():
    """Lazily build a Fernet (or MultiFernet) using the resolved key(s).

    Lazy so that test runs which never touch the legacy_* fields don't
    require the ``cryptography`` extra to be importable. Re-resolved on
    every call so key rotation via env var picks up without process
    restart in dev (production sets the env at boot, so re-resolution
    is cheap).

    v3.33.0: when ``settings.DJANGO_CRYPTOGRAPHY_KEYS`` carries more
    than one entry, returns a ``MultiFernet`` that **encrypts under the
    first (newest) key** and **decrypts under any** key in the list.
    This is the rotation grace pattern — older ciphertexts continue to
    open while new writes already use the new key.
    """
    from cryptography.fernet import Fernet, MultiFernet  # local import: optional at module load
    keys = _resolve_fernet_key_list()
    if len(keys) >= 2:
        return MultiFernet([Fernet(k) for k in keys])
    return Fernet(_resolve_fernet_key())


# ---------------------------------------------------------------------------
# Internal shim: encrypted CharField + JSONField
# ---------------------------------------------------------------------------

class EncryptedCharField(models.CharField):
    """CharField whose stored bytes are Fernet ciphertext.

    Reads transparently decrypt; writes transparently encrypt. The DB
    column is the same shape (CharField/TEXT) — we just inflate the
    stored value. Existing migration 0032 set max_length=512 so there is
    headroom for the Fernet expansion overhead (~57 bytes plaintext-fixed
    plus base64 overhead) on the typical 64-128 byte foreign-vendor
    hashes we encrypt.

    Empty string round-trips as empty string (not encrypted) so the
    "no legacy hash" sentinel doesn't waste ciphertext bytes.
    """

    description = "Fernet-encrypted CharField"

    def from_db_value(self, value: Any, expression, connection) -> Any:
        if value is None or value == "":
            return value
        try:
            return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except Exception:  # noqa: BLE001 - cryptography raises InvalidToken/TypeError
            # Honest behaviour: a row with a bad/foreign ciphertext (or
            # one written before encryption was enabled) returns the raw
            # value. Callers (the verifier) treat this as "no match"
            # because the bytes won't decode to a valid foreign-hash
            # format. NEVER log the bytes themselves.
            logger.info(
                "encrypted_charfield_decrypt_skipped",
                extra={"reason": "invalid_or_plaintext_value"},
            )
            return value

    def to_python(self, value: Any) -> Any:
        # to_python is called for form input and for already-decoded
        # values coming back from forms. We accept plaintext (str) and
        # round-trip it; the actual encryption happens in get_prep_value.
        return value

    def get_prep_value(self, value: Any) -> Any:
        # Never persist SQL NULL — CharField columns are NOT NULL with default="".
        if value is None or value == "":
            return ""
        if not isinstance(value, str):
            value = str(value)
        return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


class EncryptedJSONField(models.JSONField):
    """JSONField that stores Fernet-encrypted JSON text in a TEXT column.

    Schema-level: we declare ``TextField`` semantics at the DB so we can
    hold the ciphertext directly. Python-level: callers see / write
    dict | list | scalar values as normal.

    Empty dict ``{}`` round-trips as the literal ``{}`` (not encrypted)
    so the "no legacy params" sentinel doesn't waste ciphertext.
    """

    description = "Fernet-encrypted JSONField"

    def db_type(self, connection):  # noqa: D401 - Django Field API
        # Always use TEXT — JSON-typed columns can't hold ciphertext.
        return "text"

    def from_db_value(self, value: Any, expression, connection) -> Any:
        if value is None or value == "" or value == "{}":
            return {} if value in (None, "", "{}") else value
        try:
            plaintext = _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except Exception:  # noqa: BLE001 - InvalidToken/TypeError
            logger.info(
                "encrypted_jsonfield_decrypt_skipped",
                extra={"reason": "invalid_or_plaintext_value"},
            )
            # Try parsing the raw value as JSON (pre-encryption row).
            try:
                return json.loads(value)
            except (ValueError, TypeError):
                return {}
        try:
            return json.loads(plaintext)
        except (ValueError, TypeError):
            return {}

    def to_python(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value

    def get_prep_value(self, value: Any) -> Any:
        if value is None or value == {} or value == "" or value == "{}":
            return "{}"
        serialized = json.dumps(value, separators=(",", ":"), sort_keys=True)
        return _get_fernet().encrypt(serialized.encode("utf-8")).decode("utf-8")


class EncryptedBinaryField(models.BinaryField):
    """BinaryField whose stored bytes are Fernet ciphertext.

    Reads transparently decrypt; writes transparently encrypt. Used by
    :class:`apps.migration_cloud.models.MigrationCloudWebhookSubscription`
    for ``secret_ciphertext`` (HMAC signing material for outbound
    webhook deliveries). The DB column shape is unchanged (BinaryField
    backing — bytea on PostgreSQL, BLOB on SQLite); only the value
    transform on read/write differs.

    Empty bytes / ``None`` round-trips as-is (no encryption pass) so
    the "no secret set" sentinel doesn't waste ciphertext bytes.

    v3.32.0: reuses the same ``_get_fernet()`` Fernet key as the
    User-model legacy_* fields. Key rotation therefore covers both
    legacy hashes AND webhook secrets in a single operator action — see
    ``docs/SECURITY_KEYS.md``.
    """

    description = "Fernet-encrypted BinaryField"

    def deconstruct(self):
        # Report as plain BinaryField so makemigrations does not see a
        # path change every time we move the encryption module. The
        # migration in this repo (0008_wrap_webhook_secret) carries the
        # one-time AlterField + RunPython that did the actual wrap; the
        # at-rest value transform is a runtime-only behavior of the
        # descriptor.
        name, _path, args, kwargs = super().deconstruct()
        return name, "django.db.models.BinaryField", args, kwargs

    def from_db_value(self, value, expression, connection):
        if value is None or value == b"" or value == "":
            return value if value is None else b""
        # Drivers may return memoryview/bytes — normalize to bytes.
        if isinstance(value, memoryview):
            value = value.tobytes()
        if not isinstance(value, (bytes, bytearray)):
            try:
                value = bytes(value)
            except (TypeError, ValueError):
                return b""
        try:
            return _get_fernet().decrypt(bytes(value))
        except Exception:  # noqa: BLE001 - InvalidToken/TypeError tolerated
            # Honest behaviour: a row written before encryption was
            # enabled (raw plaintext bytes) round-trips unchanged so
            # the migration's RunPython forward can re-wrap it. NEVER
            # log the raw bytes themselves.
            logger.info(
                "encrypted_binaryfield_decrypt_skipped",
                extra={"reason": "invalid_or_plaintext_value"},
            )
            return bytes(value)

    def to_python(self, value):
        return value

    def get_prep_value(self, value):
        if value is None:
            return None
        if value == b"" or value == "":
            return b""
        if isinstance(value, memoryview):
            value = value.tobytes()
        if isinstance(value, str):
            value = value.encode("utf-8")
        if not isinstance(value, (bytes, bytearray)):
            try:
                value = bytes(value)
            except (TypeError, ValueError):
                return b""
        return _get_fernet().encrypt(bytes(value))


# ---------------------------------------------------------------------------
# Public surface — used by the User model + migration 0033
# ---------------------------------------------------------------------------

def encrypt_charfield(**field_kwargs: Any):
    """Return a CharField-compatible field that encrypts at rest.

    Used by the User model and by migration 0033's AlterField op. When
    the upstream django-cryptography package is importable on the
    running Django version, the upstream encrypt() decorator is used so
    we inherit any future hardening. Otherwise the internal Fernet
    shim above is used.
    """
    if _USE_UPSTREAM:
        base_field = models.CharField(**field_kwargs)
        return _upstream_encrypt(base_field)
    return EncryptedCharField(**field_kwargs)


def encrypt_jsonfield(**field_kwargs: Any):
    """Return a JSONField-compatible field that encrypts at rest."""
    if _USE_UPSTREAM:
        base_field = models.JSONField(**field_kwargs)
        return _upstream_encrypt(base_field)
    return EncryptedJSONField(**field_kwargs)


def encrypt_binaryfield(**field_kwargs: Any):
    """Return a BinaryField-compatible field that encrypts at rest.

    Used by :class:`apps.migration_cloud.models.MigrationCloudWebhookSubscription`
    for ``secret_ciphertext`` (v3.32.0). The upstream path falls back to
    the internal shim because django-cryptography 1.x's ``encrypt()``
    helper targets text-shaped fields — BinaryField goes through the
    Fernet shim directly so the round-trip stays bytes-typed.
    """
    return EncryptedBinaryField(**field_kwargs)


def backend_in_use() -> str:
    """Return a short slug for the active encryption backend.

    Used by tests + the encryption backfill script to surface which
    code path executed. NOT logged with any secret material.
    """
    return "django_cryptography_upstream" if _USE_UPSTREAM else "internal_fernet_shim"


def active_key_count() -> int:
    """Return how many Fernet keys are currently active.

    1 = single-key (no rotation in flight). 2+ = MultiFernet rotation
    grace period. 0 = SECRET_KEY-derived dev fallback. Used by the
    rotation tooling + the operator beat for visibility. NEVER logs
    key material.
    """
    return len(_resolve_fernet_key_list())


def _get_primary_fernet():
    """Return a single-key Fernet built from the NEWEST key only.

    Used by the rotation code path: re-encrypt with this so the
    resulting ciphertext is solely under the new primary key (no
    MultiFernet token-version ambiguity).
    """
    from cryptography.fernet import Fernet  # local import: optional at module load
    return Fernet(_resolve_fernet_key())
