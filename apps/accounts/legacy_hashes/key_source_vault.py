"""SH-6 — env-driven HashiCorp Vault KV v2 source for the field-encryption key
ring (``DJANGO_CRYPTOGRAPHY_KEYS``).

This closes the SH-6 self-host gap from the 2026-06-03 open-source posture audit:
before this, platform field-encryption keys could only come from env vars, while
only the migration-cloud audit-signing key could live in Vault. Now an operator
can source the whole MultiFernet key ring from Vault — **opt-in, default off**.

Default behavior is UNCHANGED: when ``DJANGO_CRYPTOGRAPHY_KEYS_SOURCE`` is unset
or ``env``, :func:`load_keys_from_vault` returns ``None`` immediately and the
existing env/settings key resolution in ``encryption._resolve_fernet_key_list``
runs exactly as before. Nothing reaches the network unless the operator opts in.

Stdlib only (``urllib`` + ``json``), mirroring
``apps/migration_cloud/services/hsm_vault.py``. NEVER logs the Vault token or any
key material.

Env contract
------------
  DJANGO_CRYPTOGRAPHY_KEYS_SOURCE    "env" (default) | "vault"
  VAULT_ADDR                         http(s):// base URL (shared with audit-signing)
  VAULT_TOKEN                        Vault token
  VAULT_NAMESPACE                    (optional) Vault Enterprise namespace
  DJANGO_CRYPTOGRAPHY_VAULT_MOUNT    KV v2 mount point (default "secret")
  DJANGO_CRYPTOGRAPHY_VAULT_PATH     secret path within the mount (required for vault)
  DJANGO_CRYPTOGRAPHY_VAULT_FIELD    field holding the ring (default "keys")
  DJANGO_CRYPTOGRAPHY_VAULT_DRY_RUN  "1" → skip network, return None (CI falls back to env)
  DJANGO_CRYPTOGRAPHY_VAULT_CACHE_SECONDS  process cache TTL (default 300)

The ring field value may be a JSON array of strings, or a comma/newline-separated
string of url-safe-base64 Fernet keys, **newest-first**.

Fail-loud contract
------------------
When ``DJANGO_CRYPTOGRAPHY_KEYS_SOURCE=vault`` and the fetch/parse fails (or
required config is missing), this raises :class:`VaultKeySourceError` rather than
silently falling back to a different key source. Silently switching key sources
would make existing ciphertext unreadable and new writes unrecoverable — so an
operator who explicitly opted into Vault gets a loud, actionable failure instead.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# HTTP ceiling — KV reads are sub-100ms in practice; 10s surfaces a dead Vault
# fast enough not to hang the encryption path.
_VAULT_HTTP_TIMEOUT_SECONDS = 10
_DEFAULT_CACHE_SECONDS = 300
# After a transient fetch error we serve the last-known-good ring and treat the
# cache as fresh for this short window, so a down Vault isn't hammered on every
# encrypt call while still retrying reasonably often.
_ERROR_RETRY_SECONDS = 30

# Process-local cache so we don't hit Vault on every encrypt/decrypt call
# (encryption._get_fernet re-resolves keys per call). Keys are NOT logged; only
# a count is cached alongside a monotonic timestamp.
_CACHE: dict[str, object] = {"keys": None, "at": 0.0}


class VaultKeySourceError(RuntimeError):
    """Raised when the operator opted into Vault key sourcing but it failed.

    Deliberately NOT swallowed by the caller — a misconfigured Vault must fail
    loudly rather than silently fall back to a different key source.
    """


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def keys_source() -> str:
    return _env("DJANGO_CRYPTOGRAPHY_KEYS_SOURCE", "env").strip().lower()


def is_vault_source() -> bool:
    return keys_source() == "vault"


def _is_dry_run() -> bool:
    return _env("DJANGO_CRYPTOGRAPHY_VAULT_DRY_RUN", "0").strip() == "1"


def _cache_ttl_seconds() -> int:
    raw = _env("DJANGO_CRYPTOGRAPHY_VAULT_CACHE_SECONDS", str(_DEFAULT_CACHE_SECONDS)).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_CACHE_SECONDS


def reset_cache_for_tests() -> None:
    """Clear the process-local key cache. Tests only."""
    _CACHE["keys"] = None
    _CACHE["at"] = 0.0


def _parse_ring(value: object) -> list[str]:
    """Normalize a KV field value into a newest-first list of key strings.

    Accepts a JSON array (already a list), or a string that is either a JSON
    array or a comma/newline-separated list. Empty entries are dropped.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip()]
            except json.JSONDecodeError:
                pass
        # Fall back to comma / newline separated.
        parts = [p.strip() for chunk in s.splitlines() for p in chunk.split(",")]
        return [p for p in parts if p]
    return []


def _build_headers(token: str, namespace: str) -> dict[str, str]:
    headers = {
        "X-Vault-Token": token,
        "Accept": "application/json",
    }
    if namespace:
        headers["X-Vault-Namespace"] = namespace
    return headers


def _redact_url_path(url: str) -> str:
    """Return only the path portion of a URL for logging (no host/query)."""
    try:
        from urllib.parse import urlsplit

        return urlsplit(url).path or "/"
    except Exception:  # noqa: BLE001
        return "/"


def _get_kv_v2(addr: str, mount: str, path: str, headers: dict[str, str]) -> dict:
    url = f"{addr}/v1/{mount}/data/{path}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_VAULT_HTTP_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        logger.warning(
            "django_cryptography_vault.http_error status=%s url_path=%s",
            getattr(exc, "code", "?"),
            _redact_url_path(url),
        )
        raise VaultKeySourceError(
            f"vault KV read HTTP error status={getattr(exc, 'code', '?')}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning(
            "django_cryptography_vault.transport_error reason=%s",
            type(exc).__name__,
        )
        raise VaultKeySourceError(
            f"vault KV transport error: {type(exc).__name__}"
        ) from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VaultKeySourceError("vault KV response was not valid JSON") from exc


def load_keys_from_vault() -> list[str] | None:
    """Return the Fernet key ring from Vault, or ``None`` to use the env path.

    * ``DJANGO_CRYPTOGRAPHY_KEYS_SOURCE`` unset / ``env`` → ``None`` (no network).
    * dry-run → ``None`` (CI falls back to env), logged once per call.
    * ``vault`` + reachable → newest-first list of key strings (cached).
    * ``vault`` + transient fetch error AND a prior ring is cached → serves the
      last-known-good ring (same source; never switches to env) + warns.
    * ``vault`` + misconfigured (bad addr / no token / no path), OR fetch error
      with no cached ring → raises :class:`VaultKeySourceError` (fail-loud).
    """
    if not is_vault_source():
        return None

    if _is_dry_run():
        logger.info("django_cryptography_vault.dry_run skipping network; using env keys")
        return None

    # Serve from cache when fresh.
    ttl = _cache_ttl_seconds()
    cached = _CACHE.get("keys")
    if cached is not None and ttl > 0:
        age = time.monotonic() - float(_CACHE.get("at", 0.0))
        if age < ttl:
            return list(cached)  # type: ignore[arg-type]

    addr = _env("VAULT_ADDR").rstrip("/")
    token = _env("VAULT_TOKEN")
    namespace = _env("VAULT_NAMESPACE")
    mount = _env("DJANGO_CRYPTOGRAPHY_VAULT_MOUNT", "secret").strip("/")
    path = _env("DJANGO_CRYPTOGRAPHY_VAULT_PATH").strip("/")
    field = _env("DJANGO_CRYPTOGRAPHY_VAULT_FIELD", "keys")

    if not (addr.startswith("http://") or addr.startswith("https://")):
        raise VaultKeySourceError(
            "DJANGO_CRYPTOGRAPHY_KEYS_SOURCE=vault but VAULT_ADDR is not an http(s):// URL."
        )
    if not token:
        raise VaultKeySourceError(
            "DJANGO_CRYPTOGRAPHY_KEYS_SOURCE=vault but VAULT_TOKEN is empty."
        )
    if not path:
        raise VaultKeySourceError(
            "DJANGO_CRYPTOGRAPHY_KEYS_SOURCE=vault but DJANGO_CRYPTOGRAPHY_VAULT_PATH is empty."
        )

    # Fetch + parse. On ANY fetch/parse failure, serve the last-known-good ring
    # if we have one (resilience against a transient Vault blip) instead of
    # bricking the encryption path. This NEVER switches key source — it keeps
    # serving the SAME Vault-sourced keys. Misconfig at cold start (no cache)
    # still fails loud. Config validation above always raises (not transient).
    try:
        body = _get_kv_v2(addr, mount, path, _build_headers(token, namespace))
        # KV v2 shape: {"data": {"data": {<field>: <value>}, "metadata": {...}}}
        try:
            secret_data = body["data"]["data"]
        except (KeyError, TypeError) as exc:
            raise VaultKeySourceError(
                "vault KV v2 response missing data.data (is the mount KV v2?)"
            ) from exc
        keys = _parse_ring(secret_data.get(field))
        if not keys:
            raise VaultKeySourceError(
                f"vault secret at '{mount}/{path}' has no usable keys in field '{field}'."
            )
    except VaultKeySourceError as exc:
        if cached is not None:
            logger.warning(
                "django_cryptography_vault.serving_stale_after_fetch_error reason=%s",
                exc,
            )
            # Throttle retries during an outage: treat the cache as fresh for a
            # short window so we don't hammer a down Vault on every encrypt call.
            _CACHE["at"] = time.monotonic() - max(0, ttl - _ERROR_RETRY_SECONDS)
            return list(cached)  # type: ignore[arg-type]
        raise

    _CACHE["keys"] = list(keys)
    _CACHE["at"] = time.monotonic()
    logger.info(
        "django_cryptography_vault.loaded ring_size=%d mount=%s field=%s",
        len(keys), mount, field,
    )
    return list(keys)


__all__ = [
    "VaultKeySourceError",
    "keys_source",
    "is_vault_source",
    "load_keys_from_vault",
    "reset_cache_for_tests",
]
