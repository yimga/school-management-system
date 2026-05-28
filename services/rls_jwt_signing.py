"""RLS-JWT signing backend selector (v4.00.0+).

Honors ``settings.RMC_RLS_JWT_SIGNING_BACKEND``:

  * ``local-env-key`` (default): HMAC-SHA256 with ``RMC_RLS_JWT_SIGNING_KEY``
    (or SECRET_KEY-derived material in dev). This is what the middleware uses
    today via the embedded ``_signing_key()`` helper.
  * ``aws-kms`` / ``azure-keyvault`` / ``hashicorp-vault`` / ``gcp-kms``:
    HSM-backed paths. These RAISE ``NotImplementedError`` until the operator
    wires up the corresponding bridge — by design. This prevents accidental
    downgrade to local key material in a production environment that has
    declared HSM intent.

The active backend is consulted by ``mint_rls_jwt`` for new tokens and by the
middleware for verification. Both call ``sign(message)`` / ``verify(message,
sig)`` here, keeping the cryptographic dispatch in one place.

This module mirrors the shape of the existing ``apps.migration_cloud.services
.audit_root_signing`` backend selector so operators already familiar with the
HSM lever in that module can read this one in 60 seconds.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import logging
from typing import Callable

from django.conf import settings

logger = logging.getLogger(__name__)

LOCAL_BACKEND = "local-env-key"
HSM_BACKENDS: frozenset[str] = frozenset({
    "aws-kms",
    "azure-keyvault",
    "hashicorp-vault",
    "gcp-kms",
})
VALID_BACKENDS: frozenset[str] = HSM_BACKENDS | {LOCAL_BACKEND}


class HSMBackendNotConfigured(NotImplementedError):
    """Raised when an HSM backend is selected but its bridge is not wired up.

    The middleware MUST NOT silently fall back to the local key — that would
    defeat the purpose of declaring HSM intent. The operator gets a hard
    failure pointing at the docs.
    """


def _resolve_backend() -> str:
    raw = (getattr(settings, "RMC_RLS_JWT_SIGNING_BACKEND", "") or "").strip()
    if raw in VALID_BACKENDS:
        return raw
    if raw:
        logger.warning(
            "rls_jwt_signing.unknown_backend=%s — falling back to %s",
            raw, LOCAL_BACKEND,
        )
    return LOCAL_BACKEND


def _local_signing_key() -> bytes:
    explicit = (getattr(settings, "RMC_RLS_JWT_SIGNING_KEY", "") or "").strip()
    if explicit:
        return explicit.encode("utf-8")
    derived = hashlib.sha256(
        (getattr(settings, "SECRET_KEY", "") + "::rmc-rls-jwt").encode("utf-8")
    ).hexdigest()
    return derived.encode("utf-8")


def _local_sign(message: bytes) -> bytes:
    return hmac.new(_local_signing_key(), message, hashlib.sha256).digest()


def _local_verify(message: bytes, signature: bytes) -> bool:
    return hmac.compare_digest(_local_sign(message), signature)


def _hsm_not_configured(backend: str) -> Callable[[bytes], bytes]:
    def _raise(_: bytes) -> bytes:
        raise HSMBackendNotConfigured(
            f"RMC_RLS_JWT_SIGNING_BACKEND={backend!r} but the bridge is not "
            f"wired up. See docs/HSM_BRIDGE.md and implement "
            f"services.rls_jwt_signing._{backend.replace('-', '_')}_signer."
        )
    return _raise


# Per-backend signer factories. To plug in a real HSM, implement the factory
# (returning a callable that does the network call) and replace the
# _hsm_not_configured wiring below.

def _aws_kms_signer() -> Callable[[bytes], bytes]:
    return _hsm_not_configured("aws-kms")


def _azure_keyvault_signer() -> Callable[[bytes], bytes]:
    return _hsm_not_configured("azure-keyvault")


def _hashicorp_vault_signer() -> Callable[[bytes], bytes]:
    return _hsm_not_configured("hashicorp-vault")


def _gcp_kms_signer() -> Callable[[bytes], bytes]:
    return _hsm_not_configured("gcp-kms")


_BACKEND_FACTORIES: dict[str, Callable[[], Callable[[bytes], bytes]]] = {
    "aws-kms": _aws_kms_signer,
    "azure-keyvault": _azure_keyvault_signer,
    "hashicorp-vault": _hashicorp_vault_signer,
    "gcp-kms": _gcp_kms_signer,
}


@functools.lru_cache(maxsize=1)
def _resolved_signer() -> Callable[[bytes], bytes]:
    backend = _resolve_backend()
    if backend == LOCAL_BACKEND:
        return _local_sign
    factory = _BACKEND_FACTORIES.get(backend)
    if factory is None:
        return _local_sign
    return factory()


def sign(message: bytes) -> bytes:
    """Sign ``message`` with the configured backend.

    Raises ``HSMBackendNotConfigured`` when an HSM backend is selected but
    not wired up.
    """
    signer = _resolved_signer()
    return signer(message)


def verify(message: bytes, signature: bytes) -> bool:
    """Verify ``signature`` against ``message`` with the configured backend.

    For the local backend this is HMAC equality. HSM backends typically do
    not have a verify operation distinct from re-sign; we therefore re-sign
    and compare in constant time. If the HSM backend is not configured this
    raises ``HSMBackendNotConfigured`` so the operator gets a hard failure.
    """
    if not signature:
        return False
    backend = _resolve_backend()
    if backend == LOCAL_BACKEND:
        return _local_verify(message, signature)
    expected = sign(message)
    return hmac.compare_digest(expected, signature)


def active_backend() -> str:
    """Public read for diagnostics + ``/super/migration/health/`` dashboard."""
    return _resolve_backend()


def reset_signer_cache() -> None:
    """Drop the LRU cache. Test helper; never called from request path."""
    _resolved_signer.cache_clear()
