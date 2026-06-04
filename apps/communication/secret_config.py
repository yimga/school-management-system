"""Transparent encryption for per-tenant channel-integration secrets.

Audit C1 (CRITICAL): WhatsApp ``access_token``, FCM ``server_key`` / service
account, push endpoint creds, etc. were stored in plaintext inside
``ServiceIntegration.config`` (a JSONField). Any DB read, backup, or
read-replica leak exposed every tenant's messaging credentials. The platform
already ships Fernet (``apps.accounts.legacy_hashes.encryption``); these
channels simply never adopted it.

This module wraps the *secret-named* keys of a config dict at the storage
boundary:

* :func:`encrypt_config` — called by ``ServiceIntegration.save()``. Secret
  values are Fernet-wrapped and prefixed with ``ENC_PREFIX`` so we can tell
  encrypted from plaintext. Idempotent (already-encrypted values are left
  alone) and backward-compatible (rows written before this lands stay
  plaintext until the next save or the ``encrypt_channel_secrets`` command).
* :func:`decrypt_config` — called at every read boundary (the channel
  resolvers). Encrypted values are unwrapped; plaintext values pass through
  unchanged, so a half-migrated table keeps working.

NEVER raises into the hot path: a decrypt failure logs a warning and returns
the value untouched (a bad credential simply fails the downstream send, which
is already handled).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

ENC_PREFIX = "enc::fernet::"

# Config keys whose VALUES are secrets and must be encrypted at rest.
SECRET_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "server_key",
        "api_key",
        "api_secret",
        "api_token",
        "auth_token",
        "twilio_auth_token",
        "client_secret",
        "private_key",
        "service_account",
        "service_account_json",
        "webhook_secret",
        "app_secret",
        "password",
        "secret",
        "verify_token",
        "shared_secret",
    }
)


def _is_secret_key(key: str) -> bool:
    k = str(key or "").lower()
    return k in SECRET_KEYS or k.endswith("_secret") or k.endswith("_token") or k.endswith("_key")


def encrypt_config(config: Any) -> Any:
    """Return a copy of ``config`` with secret-named string values encrypted.

    Idempotent: values already carrying ``ENC_PREFIX`` are left as-is.
    """
    if not isinstance(config, dict):
        return config
    try:
        from apps.schoolops.email_delivery import encrypt_password_for_storage
    except Exception:  # noqa: BLE001 — crypto layer absent → store as-is (logged)
        logger.warning("communication.secret_config.encrypt_unavailable")
        return config
    out = dict(config)
    for key, value in list(out.items()):
        if not _is_secret_key(key):
            continue
        if not isinstance(value, str) or not value:
            continue
        if value.startswith(ENC_PREFIX):
            continue
        try:
            out[key] = ENC_PREFIX + encrypt_password_for_storage(value)
        except Exception:  # noqa: BLE001 — never lose the value; leave plaintext
            logger.error("communication.secret_config.encrypt_failed key=%s", key)
    return out


def decrypt_config(config: Any) -> Any:
    """Return a copy of ``config`` with encrypted secret values unwrapped.

    Plaintext (un-prefixed) values pass through unchanged so a partially
    migrated table keeps working.
    """
    if not isinstance(config, dict):
        return config
    out = dict(config)
    fernet = None
    for key, value in list(out.items()):
        if not isinstance(value, str) or not value.startswith(ENC_PREFIX):
            continue
        token = value[len(ENC_PREFIX):]
        try:
            if fernet is None:
                from apps.accounts.legacy_hashes.encryption import _get_fernet

                fernet = _get_fernet()
            out[key] = fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except Exception:  # noqa: BLE001 — leave wrapped; downstream send fails cleanly
            logger.warning("communication.secret_config.decrypt_failed key=%s", key)
    return out


__all__ = ["encrypt_config", "decrypt_config", "SECRET_KEYS", "ENC_PREFIX"]
