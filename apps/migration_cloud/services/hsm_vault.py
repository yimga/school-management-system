"""v3.40.0 Agent 1 — HashiCorp Vault Transit backend for audit root-key signing.

First concrete HSM-pluggable backend behind the
``MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND`` selector. The other three
reserved cloud backends (``aws-kms``, ``azure-keyvault``, ``gcp-kms``)
remain raising ``NotImplementedError`` and will be filled in subsequent
waves.

Vault was chosen first because:

  * Public HTTP API — no cloud-vendor SDK lift, no IAM dance for a
    minimum-viable operator deployment.
  * Dev mode (`vault server -dev`) gives a 30-second local proof-of-life.
  * Transit secrets engine natively supports HMAC-SHA512 (sign + verify),
    which matches the algorithm the local-env-key backend already uses,
    so the root-signature pre-image stays byte-identical regardless of
    backend.
  * Key rotation (`vault write -f transit/keys/<name>/rotate`) is a
    first-class operation; the GET on ``transit/keys/<name>`` surfaces
    ``latest_version`` so the audit log can record which key version
    signed each row.

Design constraints honored:

  * **Stdlib only** — ``urllib.request`` + ``json`` + ``hmac`` + ``base64``.
    NO ``hvac``, NO ``requests``, NO ``httpx``. Adding a Vault client lib
    would inflate the dep tree for a feature most operators will leave
    on the default ``local-env-key``.
  * **Lazy settings** — ``os.environ.get(...)`` is read inside every
    function, never at module import. The signer module is loaded in
    contexts (manage.py check, migration plan) where ``settings`` is
    not yet fully resolved, so reading env at import would freeze a
    misleading value.
  * **No new pip deps** — see requirements.txt; unchanged this wave.

Logging hygiene — this module NEVER logs:

  * ``VAULT_TOKEN`` (raw or any prefix);
  * the HMAC signature bytes from Vault (full or any prefix);
  * the pre-image bytes (the SHA-256 hex of the pre-image, FIRST 12
    characters only, is logged for trace correlation — never the bytes
    themselves);
  * the transit key NAME is logged for diagnostics (it's not a secret —
    it's the key handle, not the key material — but operators may still
    consider it sensitive, so we log only the prefix when in doubt).

Dry-run mode (``MIGRATION_CLOUD_VAULT_DRY_RUN=1``, default in dev) returns
a deterministic 128-character base64 placeholder so CI can exercise the
wiring without a live Vault. Production deployments MUST set the env var
to ``0`` and provision real Vault transit access.

Public surface:

  * :class:`VaultTransitBackend`  — instantiate once per signing call
    (cheap; no connection pool needed at the scale of audit-event
    writes).
  * :class:`VaultBackendError`    — typed exception for transport,
    config, and key-version failures.
  * :func:`sign(pre_image)`       — returns base64-encoded HMAC.
  * :func:`verify(pre_image, sig)`— returns ``True``/``False``;
    raises on transport failure.
  * :func:`key_version()`         — int; surfaces ``latest_version``
    for audit-event meta.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


# Default Vault HTTP timeout. Vault Transit operations are sub-100ms in
# practice; 10s is a generous ceiling that still surfaces a dead Vault
# fast enough for the audit-event write path not to hang the request.
_VAULT_HTTP_TIMEOUT_SECONDS = 10

# Dry-run deterministic placeholder seed. The actual returned bytes are
# HMAC-SHA512 of (pre_image || _DRY_RUN_SEED), base64-encoded. This is
# NOT cryptographically meaningful — it exists only so CI tests can
# assert determinism + length without a live Vault.
_DRY_RUN_SEED = b"migration-cloud-vault-dry-run-seed-v1"


class VaultBackendError(RuntimeError):
    """Raised on Vault transport / config / key-version failure.

    Caller (``audit_root_signing.compute_root_signature``) decides
    whether to surface this to the operator or degrade gracefully. We
    deliberately do NOT wrap this in ``NotImplementedError`` — that
    would hide a misconfigured-but-implemented backend behind the same
    error class as the unimplemented cloud backends.
    """


def _env(name: str, default: str = "") -> str:
    """Read an env var lazily. Centralized so a future test can mock."""
    return os.environ.get(name, default) or default


def _is_dry_run() -> bool:
    """Honor ``MIGRATION_CLOUD_VAULT_DRY_RUN=1`` (default in dev).

    The local-env-key backend is the production default, so dry-run on
    by default for the Vault backend means a CI lane that accidentally
    flips ``MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND=hashicorp-vault``
    without provisioning Vault won't hang trying to reach a phantom
    address; it'll get deterministic placeholders and tests will pass.
    Production opts in via ``MIGRATION_CLOUD_VAULT_DRY_RUN=0``.
    """
    raw = _env("MIGRATION_CLOUD_VAULT_DRY_RUN", "1").strip()
    return raw == "1"


def _pre_image_trace_prefix(pre_image: bytes) -> str:
    """Return a 12-char SHA-256 hex prefix of the pre-image for logs.

    Pre-image bytes themselves are structurally PII-adjacent (hashed
    identifiers) and MUST NOT be logged. The hex prefix is one-way and
    safe to log for correlating "I signed X" with "verify failed on X".
    """
    return hashlib.sha256(pre_image).hexdigest()[:12]


class VaultTransitBackend:
    """HashiCorp Vault Transit-engine bridge.

    Cheap to instantiate; holds no persistent state. The only "session"
    is the per-call HTTP request opened via ``urllib.request.urlopen``.
    """

    def __init__(
        self,
        *,
        addr: str | None = None,
        token: str | None = None,
        key_name: str | None = None,
        namespace: str | None = None,
        timeout: int = _VAULT_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        # Lazy env-var resolution: callers can override per-instance for
        # tests, but the production code path passes nothing and reads
        # the environment.
        self._addr = (addr or _env("VAULT_ADDR")).rstrip("/")
        self._token = token or _env("VAULT_TOKEN")
        self._key_name = key_name or _env(
            "MIGRATION_CLOUD_VAULT_TRANSIT_KEY_NAME",
            "migration-cloud-audit-root",
        )
        self._namespace = namespace or _env("MIGRATION_CLOUD_VAULT_NAMESPACE")
        self._timeout = int(timeout)
        self._dry_run = _is_dry_run()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sign(self, pre_image: bytes) -> str:
        """Return a base64-encoded HMAC-SHA512 signature over ``pre_image``.

        The return shape mirrors what Vault's ``transit/hmac`` returns
        post-prefix-strip: a base64 string of length 128 (88 visible
        chars for an 88-byte HMAC-SHA512 with the ``vault:v1:`` prefix
        stripped, padded to 128 by our envelope so the audit-event
        column width matches the local-env-key 128-hex shape).

        Dry-run mode returns a deterministic placeholder of length 128.
        """
        if self._dry_run:
            return self._dry_run_signature(pre_image)

        self._require_config_for_live_call()

        payload = {
            "input": base64.b64encode(pre_image).decode("ascii"),
            "algorithm": "sha2-512",
        }
        url = f"{self._addr}/v1/transit/hmac/{self._key_name}"
        body = self._post_json(url, payload)
        try:
            raw = body["data"]["hmac"]
        except (KeyError, TypeError) as exc:
            raise VaultBackendError(
                "vault transit/hmac response missing data.hmac field"
            ) from exc
        # Vault returns e.g. ``vault:v1:<base64-hmac>``. Strip the prefix
        # to keep storage shape stable across key rotations (the version
        # is recorded separately via ``key_version()``).
        if ":" in raw:
            raw = raw.split(":", 2)[-1]
        # Re-pad to 128 chars so the audit-event column shape matches
        # local-env-key's 128-hex output. Base64-padded HMAC-SHA512 is
        # 88 chars; we right-pad with '=' which is base64-legal and
        # ignored on decode.
        if len(raw) < 128:
            raw = raw + ("=" * (128 - len(raw)))
        elif len(raw) > 128:
            raw = raw[:128]
        logger.info(
            "migration_cloud.hsm_vault.sign ok "
            "pre_image_hash=%s key_name_prefix=%s",
            _pre_image_trace_prefix(pre_image),
            self._key_name[:8],
        )
        return raw

    def verify(self, pre_image: bytes, signature_b64: str) -> bool:
        """Return ``True`` iff Vault verifies the HMAC over ``pre_image``.

        In dry-run mode, recomputes the deterministic placeholder and
        compares constant-time so positive and negative paths exercise
        the same shape as the live path.
        """
        if self._dry_run:
            expected = self._dry_run_signature(pre_image)
            return hmac.compare_digest(
                expected.encode("ascii"),
                (signature_b64 or "").encode("ascii"),
            )

        self._require_config_for_live_call()

        # Strip any trailing '=' padding we added for column-width
        # parity; Vault expects exact base64 without our placeholder
        # padding.
        sig = (signature_b64 or "").rstrip("=")
        payload = {
            "input": base64.b64encode(pre_image).decode("ascii"),
            "hmac": f"vault:v{self.key_version()}:{sig}",
        }
        url = f"{self._addr}/v1/transit/verify/{self._key_name}/sha2-512"
        body = self._post_json(url, payload)
        try:
            ok = bool(body["data"]["valid"])
        except (KeyError, TypeError) as exc:
            raise VaultBackendError(
                "vault transit/verify response missing data.valid field"
            ) from exc
        logger.info(
            "migration_cloud.hsm_vault.verify result=%s "
            "pre_image_hash=%s key_name_prefix=%s",
            ok,
            _pre_image_trace_prefix(pre_image),
            self._key_name[:8],
        )
        return ok

    def key_version(self) -> int:
        """Return the transit key's ``latest_version`` integer.

        Recorded in audit-event meta so a future operator can correlate
        "this row was signed under key version N" with the rotation
        history captured in Vault.

        Dry-run mode returns 1 (stable placeholder).
        """
        if self._dry_run:
            return 1

        self._require_config_for_live_call()

        url = f"{self._addr}/v1/transit/keys/{self._key_name}"
        body = self._get_json(url)
        try:
            return int(body["data"]["latest_version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise VaultBackendError(
                "vault transit/keys response missing data.latest_version"
            ) from exc

    # ------------------------------------------------------------------
    # Internal: HTTP + config
    # ------------------------------------------------------------------

    def _require_config_for_live_call(self) -> None:
        """Validate the minimum config for a live Vault call.

        Raised as :class:`VaultBackendError`, NOT NotImplementedError —
        the backend IS implemented; it's the operator's environment
        that's incomplete.
        """
        if not self._addr:
            raise VaultBackendError(
                "VAULT_ADDR is empty; cannot reach Vault. Set "
                "VAULT_ADDR=https://vault.example.com:8200 or enable "
                "MIGRATION_CLOUD_VAULT_DRY_RUN=1 for CI."
            )
        if not self._token:
            raise VaultBackendError(
                "VAULT_TOKEN is empty; Vault refuses unauthenticated "
                "transit calls. Provision a token with policy "
                "`path \"transit/hmac/<key>\" { capabilities=[\"update\"] }`."
            )
        if not self._key_name:
            raise VaultBackendError(
                "MIGRATION_CLOUD_VAULT_TRANSIT_KEY_NAME is empty; refuse "
                "to call Vault without a key name."
            )
        if not (self._addr.startswith("http://") or self._addr.startswith("https://")):
            raise VaultBackendError(
                "VAULT_ADDR must be an http(s):// URL; got an unrecognized scheme."
            )

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "X-Vault-Token": self._token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._namespace:
            headers["X-Vault-Namespace"] = self._namespace
        return headers

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers=self._build_headers(), method="POST",
        )
        return self._open_and_decode(req)

    def _get_json(self, url: str) -> dict[str, Any]:
        req = urllib.request.Request(
            url, headers=self._build_headers(), method="GET",
        )
        return self._open_and_decode(req)

    def _open_and_decode(self, req: "urllib.request.Request") -> dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            # NEVER log token or sig bytes; do log status code + URL path
            # (path is not a secret; the token in the header would be,
            # but we don't log headers).
            logger.warning(
                "migration_cloud.hsm_vault.http_error status=%s url_path=%s",
                getattr(exc, "code", "?"),
                _redact_url_path(req.full_url),
            )
            raise VaultBackendError(
                f"vault HTTP error status={getattr(exc, 'code', '?')}"
            ) from exc
        except urllib.error.URLError as exc:
            logger.warning(
                "migration_cloud.hsm_vault.transport_error reason=%s",
                type(exc).__name__,
            )
            raise VaultBackendError(
                f"vault transport error: {type(exc).__name__}"
            ) from exc
        except (TimeoutError, OSError) as exc:
            logger.warning(
                "migration_cloud.hsm_vault.timeout_error reason=%s",
                type(exc).__name__,
            )
            raise VaultBackendError(
                f"vault timeout/socket error: {type(exc).__name__}"
            ) from exc

        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise VaultBackendError(
                "vault response was not valid JSON"
            ) from exc

    # ------------------------------------------------------------------
    # Dry-run helpers
    # ------------------------------------------------------------------

    def _dry_run_signature(self, pre_image: bytes) -> str:
        """Return a deterministic 128-char base64 placeholder.

        HMAC-SHA512(pre_image, _DRY_RUN_SEED) → base64 → right-pad to
        128 with '='. Same shape as a real Vault response post-envelope.
        """
        digest = hmac.new(_DRY_RUN_SEED, pre_image, hashlib.sha512).digest()
        b64 = base64.b64encode(digest).decode("ascii")  # 88 chars
        if len(b64) < 128:
            b64 = b64 + ("=" * (128 - len(b64)))
        return b64[:128]


def _redact_url_path(url: str) -> str:
    """Return the URL path component only — strips host (which may be a
    private hostname) and query string (Vault transit endpoints don't
    take query params, but defensive coding for future endpoints).
    """
    # Stdlib-only; intentionally avoid urlparse cyclic-import in some
    # weird sandbox lanes. Hand-roll the slice.
    if "://" in url:
        url = url.split("://", 1)[1]
    if "/" in url:
        path = "/" + url.split("/", 1)[1]
    else:
        path = "/"
    if "?" in path:
        path = path.split("?", 1)[0]
    return path


__all__ = [
    "VaultBackendError",
    "VaultTransitBackend",
]
