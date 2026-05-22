"""Wave 9 Agent N (v3.58.x) — HSM bridge interface scaffold for audit-root signing.

Per v3.39.0 `services/audit_root_signing.py`, the 3 still-reserved
HSM backends (`aws-kms`, `azure-keyvault`, `gcp-kms`) raise
`NotImplementedError` with a runbook pointer. (`hashicorp-vault` is
already implemented at v3.40.0 via :mod:`services.hsm_vault`.) This
module ships the per-backend INTERFACE that a future implementer wires
to the actual SDK — a class per backend with `sign(payload) -> bytes`
and `verify(payload, signature) -> bool` methods that currently raise
NotImplementedError but expose a stable shape callers + tests can rely
on once the SDK code is filled in.

Wiring policy (already enforced upstream in :mod:`audit_root_signing`):

  * The dispatching call site checks the backend selector setting
    `MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND`. When it equals one of the
    reserved values (`aws-kms` / `azure-keyvault` / `gcp-kms`), the
    upstream `_resolve_signing_key()` raises NotImplementedError; the
    intent is to refuse silent downgrade. This module is the place to
    BUILD OUT the actual implementation when the operator unblocks a
    backend.

Each backend class is constructable with no arguments today (the
default constructor reads its own configuration from settings + env);
when a customer asks for a specific backend the implementer fills in
the SDK initialization and replaces the body of `sign` / `verify`.

Logging hygiene: NO method in this module logs key material, signed
payload bytes, or signature bytes. Only backend-selector identifiers +
exception type names.
"""
from __future__ import annotations

import logging
from typing import Final, Protocol

logger = logging.getLogger(__name__)


_RUNBOOK_POINTER: Final[str] = "docs/HSM_BRIDGE.md"


class HSMSignerBackend(Protocol):
    """Structural type the dispatcher consumes for any HSM backend.

    All concrete backends implement these two methods plus a
    `backend_id` class-level string used for log discriminator
    purposes. The same signature shape lets the dispatcher hand off
    without caring which backend it has.
    """

    backend_id: str

    def sign(self, payload: bytes) -> bytes:
        ...

    def verify(self, payload: bytes, signature: bytes) -> bool:
        ...


def _refuse(backend_id: str) -> "NotImplementedError":
    """Return a `NotImplementedError` with a runbook pointer."""
    return NotImplementedError(
        f"HSM backend {backend_id!r} is not yet implemented — "
        f"configure HSM bridge first. See {_RUNBOOK_POINTER}."
    )


class AWSKMSSigner:
    """AWS Key Management Service backend (reserved — not implemented).

    Production wiring (when implemented):

      * uses `boto3.client("kms")` against the IAM role attached to
        the runtime;
      * the KMS key is configured via setting
        `MIGRATION_CLOUD_AUDIT_HSM_AWS_KMS_KEY_ID` (ARN or alias);
      * `sign` calls `client.sign(KeyId=..., MessageType="RAW",
        SigningAlgorithm="HMAC_SHA_512", Message=payload)` and returns
        the signature bytes;
      * `verify` calls `client.verify(...)` symmetrically. (HMAC keys
        in KMS are symmetric; sign + verify use the same key.)

    See docs/HSM_BRIDGE.md § "AWS KMS" for the IAM policy template +
    key-policy template + boto3 install snippet.
    """

    backend_id: str = "aws-kms"

    def sign(self, payload: bytes) -> bytes:
        raise _refuse(self.backend_id)

    def verify(self, payload: bytes, signature: bytes) -> bool:
        raise _refuse(self.backend_id)


class AzureKeyVaultSigner:
    """Azure Key Vault backend (reserved — not implemented).

    Production wiring (when implemented):

      * uses `azure.keyvault.keys.crypto.CryptographyClient` against
        the managed-identity attached to the runtime;
      * the vault key is configured via setting
        `MIGRATION_CLOUD_AUDIT_HSM_AZURE_VAULT_KEY_URL`;
      * `sign` calls `client.sign(SignatureAlgorithm.hs512, payload)`
        and returns `result.signature`;
      * `verify` calls `client.verify(...)` symmetrically.

    See docs/HSM_BRIDGE.md § "Azure Key Vault" for the
    managed-identity template + key-permissions ACL + az-cli snippet.
    """

    backend_id: str = "azure-keyvault"

    def sign(self, payload: bytes) -> bytes:
        raise _refuse(self.backend_id)

    def verify(self, payload: bytes, signature: bytes) -> bool:
        raise _refuse(self.backend_id)


class HashiCorpVaultSigner:
    """HashiCorp Vault Transit secret-engine backend (interface stub).

    NOTE: this scaffold COEXISTS with the production-implemented
    backend at :mod:`apps.migration_cloud.services.hsm_vault` shipped
    at v3.40.0. The dispatcher in `audit_root_signing.py` continues to
    use the production module — this stub is preserved as part of the
    HSM bridge interface family for symmetry. It deliberately raises
    NotImplementedError so future implementers do NOT mistake it for
    the production code path.

    If a customer needs a SECOND Vault flavor (e.g. PKCS#11 plugin),
    that work happens here rather than in the existing module.
    """

    backend_id: str = "hashicorp-vault-stub"

    def sign(self, payload: bytes) -> bytes:
        raise NotImplementedError(
            "HashiCorp Vault stub interface — production backend lives "
            "in apps.migration_cloud.services.hsm_vault. Only override "
            "this class if you are wiring a *second* Vault flavor."
        )

    def verify(self, payload: bytes, signature: bytes) -> bool:
        raise NotImplementedError(
            "HashiCorp Vault stub interface — production backend lives "
            "in apps.migration_cloud.services.hsm_vault. Only override "
            "this class if you are wiring a *second* Vault flavor."
        )


class GCPKMSSigner:
    """Google Cloud KMS backend (reserved — not implemented).

    Production wiring (when implemented):

      * uses `google.cloud.kms.KeyManagementServiceClient` against the
        workload-identity attached to the runtime;
      * the KMS key resource is configured via setting
        `MIGRATION_CLOUD_AUDIT_HSM_GCP_KMS_KEY_NAME` (full resource
        name `projects/.../locations/.../keyRings/.../cryptoKeys/...`);
      * `sign` calls `client.mac_sign(name=..., data=payload)` and
        returns `response.mac`;
      * `verify` calls `client.mac_verify(...)` symmetrically.

    See docs/HSM_BRIDGE.md § "GCP KMS" for the workload-identity
    template + key-ring layout + gcloud snippet.
    """

    backend_id: str = "gcp-kms"

    def sign(self, payload: bytes) -> bytes:
        raise _refuse(self.backend_id)

    def verify(self, payload: bytes, signature: bytes) -> bool:
        raise _refuse(self.backend_id)


# ─── factory ─────────────────────────────────────────────────────────────


_BACKEND_REGISTRY: Final[dict[str, type]] = {
    AWSKMSSigner.backend_id: AWSKMSSigner,
    AzureKeyVaultSigner.backend_id: AzureKeyVaultSigner,
    GCPKMSSigner.backend_id: GCPKMSSigner,
    # Vault stub registered under its OWN id so it doesn't collide
    # with the production `hashicorp-vault` backend.
    HashiCorpVaultSigner.backend_id: HashiCorpVaultSigner,
}


def get_hsm_signer(backend_id: str) -> HSMSignerBackend:
    """Return the HSM signer instance for ``backend_id``.

    Raises :class:`ValueError` when the backend id is unknown. Each
    returned instance currently raises NotImplementedError from its
    methods — call sites should treat that as the "operator must
    configure HSM bridge first" signal.

    Importantly, the production `hashicorp-vault` backend is NOT
    served from this factory. See module docstring; the dispatcher
    in :mod:`audit_root_signing` handles that path natively via
    :mod:`hsm_vault`.
    """
    cls = _BACKEND_REGISTRY.get(backend_id)
    if cls is None:
        raise ValueError(
            f"unknown HSM backend id {backend_id!r}; known: "
            f"{sorted(_BACKEND_REGISTRY.keys())!r}"
        )
    return cls()


__all__ = [
    "AWSKMSSigner",
    "AzureKeyVaultSigner",
    "GCPKMSSigner",
    "HashiCorpVaultSigner",
    "HSMSignerBackend",
    "get_hsm_signer",
]
