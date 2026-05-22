# HSM Bridge Integration Recipes (Wave 9 Agent N, v3.58.x)

Per-backend integration recipes for the audit-root-signing HSM family.
The dispatcher lives at `apps/migration_cloud/services/audit_root_signing.py`;
the per-backend interface stubs at
`apps/migration_cloud/services/audit_root_signing_hsm.py`. The
production HashiCorp Vault backend lives at
`apps/migration_cloud/services/hsm_vault.py` (shipped v3.40.0).

This document covers the 3 still-reserved backends: **AWS KMS**,
**Azure Key Vault**, **GCP KMS** — plus trust-model + cost
considerations + cross-link back to the security keys SOT.

Owner: founder / security-ops.
Status: SCAFFOLD READY (Wave 9, 2026-05-22). Each backend's `sign` +
`verify` methods raise `NotImplementedError` today. Implementing one
unblocks the corresponding `MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND`
setting value.

---

## 0. Why we need an HSM bridge at all

The Migration Cloud append-only audit log (`MigrationCloudAuditEvent`,
v3.38.0 Agent 5) records every sensitive event (companion upload, MAA
sign, key rotation, etc.) with two integrity layers:

1. **`integrity_hash`** — SHA-256 hash of a canonical-JSON
   representation of the event row + the previous event's hash (the
   per-tenant chain). Anyone with read access to the DB can recompute
   and verify the chain. This catches casual tampering.
2. **`root_key_signature`** — HMAC-SHA512 over the same canonical
   pre-image, keyed by a secret that lives **outside the database**.
   An attacker who restores from a tampered backup may have valid
   `integrity_hash` values, but cannot forge the `root_key_signature`
   unless they also compromise the signing key.

The signing key has three places it can live:

* `local-env-key` (default) — bytes in an env var. Adequate for
  small / single-instance deployments; key material is recoverable by
  anyone with shell access to the runtime.
* `hashicorp-vault` (implemented v3.40.0) — Vault Transit secret
  engine. Sign + verify happen remotely; key bytes never appear in
  the runtime.
* `aws-kms` / `azure-keyvault` / `gcp-kms` (reserved — this document
  describes how to implement them).

The HSM family is for customers who require:

* the key to live in cloud-native HSM (FIPS 140-2/3 Level 2 or 3);
* the runtime to NEVER hold key bytes — only short-lived OIDC /
  managed-identity tokens that authorize remote sign / verify calls;
* an auditable cloud-provider trail of every sign + verify operation.

---

## 1. AWS KMS

### 1.1. Key creation

KMS supports HMAC keys natively (since 2022). Create a `HMAC_512` key:

```
aws kms create-key \
  --customer-master-key-spec HMAC_512 \
  --key-usage GENERATE_VERIFY_MAC \
  --description "RunMyCampus Migration Cloud audit root signing key"
```

Note the resulting `KeyId` (UUID) and `Arn`.

### 1.2. IAM role + key-policy template

Attach an IAM role to the runtime (EC2 instance profile, EKS pod
identity, Lambda execution role, or ECS task role) with the following
*minimum* policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["kms:GenerateMac", "kms:VerifyMac"],
      "Resource": "arn:aws:kms:<region>:<acct>:key/<key-id>"
    }
  ]
}
```

The KMS key's own policy MUST also explicitly authorize the role:

```json
{
  "Sid": "AllowRunMyCampusRuntime",
  "Effect": "Allow",
  "Principal": {"AWS": "arn:aws:iam::<acct>:role/<runtime-role>"},
  "Action": ["kms:GenerateMac", "kms:VerifyMac"],
  "Resource": "*"
}
```

### 1.3. Runtime configuration

```
MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND=aws-kms
MIGRATION_CLOUD_AUDIT_HSM_AWS_KMS_KEY_ID=arn:aws:kms:us-west-2:...:key/...
```

### 1.4. SDK install

```
pip install 'boto3>=1.34,<2'
```

(boto3 is a heavy dep; gate the import behind a lazy `import boto3`
inside `AWSKMSSigner.sign` / `.verify` so customers who don't use this
backend don't pay the import cost.)

### 1.5. Implementation sketch

```python
class AWSKMSSigner:
    backend_id = "aws-kms"

    def __init__(self):
        import boto3
        from django.conf import settings
        self._key_id = settings.MIGRATION_CLOUD_AUDIT_HSM_AWS_KMS_KEY_ID
        self._client = boto3.client("kms")

    def sign(self, payload: bytes) -> bytes:
        resp = self._client.generate_mac(
            KeyId=self._key_id,
            MacAlgorithm="HMAC_SHA_512",
            Message=payload,
        )
        return resp["Mac"]

    def verify(self, payload: bytes, signature: bytes) -> bool:
        try:
            self._client.verify_mac(
                KeyId=self._key_id,
                MacAlgorithm="HMAC_SHA_512",
                Message=payload,
                Mac=signature,
            )
            return True
        except self._client.exceptions.KMSInvalidMacException:
            return False
```

### 1.6. Trust model + caveats

* Sign + verify each cost one KMS request — pricing as of 2026-Q2
  is ~$0.03 per 10,000 requests. At 100k events/day → ~$0.30/day.
* AWS KMS throttling is 5,500 RPS by default per account; burst
  protection on the audit-event write path is the operator's
  responsibility (see v3.40.0 Agent 14 per-tenant rate limit).
* IAM role rotation is the customer's standard procedure; no key
  bytes ever land in the runtime.

---

## 2. Azure Key Vault

### 2.1. Key creation

Azure Key Vault supports HMAC-SHA512 via the "octet keys" surface
(Key Vault Managed HSM tier; the Standard tier does not include HMAC
signing). Create a key:

```
az keyvault key create \
  --vault-name <vault> \
  --name rmc-audit-root-key \
  --kty oct-HSM \
  --size 256
```

### 2.2. Managed identity + access policy

Assign a system-assigned (or user-assigned) managed identity to the
runtime (Azure App Service / AKS / VM). Grant key permissions:

```
az keyvault set-policy \
  --name <vault> \
  --object-id <runtime-mi-object-id> \
  --key-permissions sign verify
```

### 2.3. Runtime configuration

```
MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND=azure-keyvault
MIGRATION_CLOUD_AUDIT_HSM_AZURE_VAULT_KEY_URL=https://<vault>.vault.azure.net/keys/rmc-audit-root-key/<version>
```

### 2.4. SDK install

```
pip install 'azure-identity>=1.15,<2' 'azure-keyvault-keys>=4.8,<5'
```

### 2.5. Implementation sketch

```python
class AzureKeyVaultSigner:
    backend_id = "azure-keyvault"

    def __init__(self):
        from django.conf import settings
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.keys.crypto import CryptographyClient
        self._key_url = settings.MIGRATION_CLOUD_AUDIT_HSM_AZURE_VAULT_KEY_URL
        self._client = CryptographyClient(
            key=self._key_url,
            credential=DefaultAzureCredential(),
        )

    def sign(self, payload: bytes) -> bytes:
        from azure.keyvault.keys.crypto import SignatureAlgorithm
        result = self._client.sign(SignatureAlgorithm.hs512, payload)
        return result.signature

    def verify(self, payload: bytes, signature: bytes) -> bool:
        from azure.keyvault.keys.crypto import SignatureAlgorithm
        result = self._client.verify(SignatureAlgorithm.hs512, payload, signature)
        return bool(result.is_valid)
```

### 2.6. Trust model + caveats

* Managed HSM tier required (Standard tier does not support HMAC
  signing).
* Sign + verify latency is ~50ms per call (region-dependent).
* Managed identity tokens are short-lived (1 hour) and refreshed
  automatically by `DefaultAzureCredential`.
* Cost: Managed HSM ~$3/hour for the pool baseline, plus per-call
  rate. Significantly more expensive than AWS KMS for low-volume
  workloads.

---

## 3. HashiCorp Vault (interface stub — production lives elsewhere)

The production-implemented HashiCorp Vault backend ships at
`apps/migration_cloud/services/hsm_vault.py` (v3.40.0). The
`HashiCorpVaultSigner` class in
`apps/migration_cloud/services/audit_root_signing_hsm.py` is a
*stub* for any future operator who needs a SECOND Vault flavor (e.g.
PKCS#11 plugin, transit + transform combo). The dispatcher in
`audit_root_signing.py` continues to use the production module.

### 3.1. When to implement the stub

Only when a customer requires Vault features beyond what the existing
Transit-engine backend covers:

* PKCS#11 plugin (FIPS 140-2 Level 3 HSM behind Vault);
* Transform secrets engine (FPE);
* Multi-region Vault with `mount_path` per region.

In that case, override `HashiCorpVaultSigner.sign` / `.verify` with
the new SDK calls. Otherwise, leave the stub as-is — its
NotImplementedError is intentional + protects against an accidental
override.

### 3.2. SDK reference

The production module uses `hvac` (HashiCorp's official Python client).
See `apps/migration_cloud/services/hsm_vault.py` for the canonical
Transit-engine sign/verify shape.

---

## 4. GCP KMS

### 4.1. Key creation

GCP KMS supports HMAC-SHA512 since 2021 via the `MAC` purpose:

```
gcloud kms keyrings create rmc-audit \
  --location global

gcloud kms keys create root-signing-key \
  --location global \
  --keyring rmc-audit \
  --purpose mac \
  --default-algorithm hmac-sha512
```

### 4.2. Workload identity + IAM

Bind a Google service account to the runtime via workload identity
(GKE / Cloud Run). Grant the `Cloud KMS CryptoKey Signer/Verifier`
role:

```
gcloud kms keys add-iam-policy-binding root-signing-key \
  --location global \
  --keyring rmc-audit \
  --member serviceAccount:<runtime-sa>@<proj>.iam.gserviceaccount.com \
  --role roles/cloudkms.signerVerifier
```

### 4.3. Runtime configuration

```
MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND=gcp-kms
MIGRATION_CLOUD_AUDIT_HSM_GCP_KMS_KEY_NAME=projects/<proj>/locations/global/keyRings/rmc-audit/cryptoKeys/root-signing-key
```

### 4.4. SDK install

```
pip install 'google-cloud-kms>=2.20,<3'
```

### 4.5. Implementation sketch

```python
class GCPKMSSigner:
    backend_id = "gcp-kms"

    def __init__(self):
        from google.cloud import kms_v1
        from django.conf import settings
        self._key_name = settings.MIGRATION_CLOUD_AUDIT_HSM_GCP_KMS_KEY_NAME
        self._client = kms_v1.KeyManagementServiceClient()

    def sign(self, payload: bytes) -> bytes:
        # GCP KMS MAC keys are versioned; we sign with the primary
        # version by name. The primary version is rotatable via
        # gcloud independently of the key name.
        resp = self._client.mac_sign(
            request={"name": f"{self._key_name}/cryptoKeyVersions/1",
                     "data": payload},
        )
        return resp.mac

    def verify(self, payload: bytes, signature: bytes) -> bool:
        resp = self._client.mac_verify(
            request={"name": f"{self._key_name}/cryptoKeyVersions/1",
                     "data": payload,
                     "mac": signature},
        )
        return bool(resp.success)
```

### 4.6. Trust model + caveats

* Pricing is the cheapest of the three cloud HSMs at ~$0.03 per
  10,000 operations + $0.06/key/month.
* GCP KMS supports automatic rotation; the key version is part of the
  resource name, so a rotation requires either pinning a version or
  walking versions on verify.

---

## 5. Trust model — what an HSM bridge does NOT prove

Important caveats common to all 4 backends:

* The HSM signs whatever bytes you hand it. It does NOT validate that
  the bytes are a "legitimate" audit event. If an attacker compromises
  the runtime's IAM role / managed identity / workload identity, they
  can forge sign() calls for arbitrary payloads. The HSM raises the
  attack cost but does not eliminate it.
* The signing key is symmetric (HMAC). The same key signs AND verifies.
  Customers who need asymmetric audit signatures (regulator-only
  verification) need a DIFFERENT scheme — likely RSA / Ed25519 with the
  public key published; the HSM bridge family does not cover that
  case. File an issue if you need it.
* Backups + restore: the chain catches tampering at the row level.
  The HSM signature catches tampering across a whole-DB restore.
  Neither catches the legitimate operator running `manage.py
  purge_audit_events_pre_approved --apply` (which is itself audited;
  see `docs/MIGRATION_CLOUD_AUDIT_LOG.md`).

---

## 6. Cost considerations

| Backend | Setup cost | Per-call cost | Notes |
|---|---|---|---|
| `local-env-key` | $0 | $0 | Default. Suitable for single-host deployments. |
| `hashicorp-vault` | Vault license / Vault Cloud | included | Production-implemented v3.40.0. |
| `aws-kms` | $1/key/month | ~$0.03/10k ops | Cheapest cloud HSM. |
| `azure-keyvault` | ~$3/hour Managed HSM baseline | ~$0.50/10k ops | Most expensive; Managed HSM tier required. |
| `gcp-kms` | $0.06/key/month | ~$0.03/10k ops | Cheapest setup; comparable per-call to AWS. |

For a 100k-event/day workload (a large school district):

* AWS KMS: ~$10/month
* Azure Key Vault: ~$2,200/month (mostly Managed HSM baseline)
* GCP KMS: ~$10/month
* Vault Cloud: depends on SKU; ~$50-500/month typical
* `local-env-key`: $0

---

## 7. Implementation checklist (when a customer asks)

1. Confirm the customer's regulatory requirement (FIPS 140-2 Level 2
   vs 3; specific cloud provider mandate; etc.).
2. Create the HSM key per § 1-4 above.
3. Implement the corresponding class in
   `apps/migration_cloud/services/audit_root_signing_hsm.py` per the
   sketch.
4. Update `apps/migration_cloud/services/audit_root_signing.py` to
   route the backend value through `get_hsm_signer()` (currently it
   raises NotImplementedError for the 3 reserved backends — move the
   raise into the per-class methods that this scaffold provides
   instead, so the dispatcher itself can be HSM-agnostic).
5. Add tests under `apps/migration_cloud/tests/test_hsm_<backend>.py`
   that mock the SDK and assert sign + verify round-trip.
6. Ship behind a default-off setting; document the operator
   procedure in `docs/SECURITY_KEYS.md` § "HSM bridges (per-backend)".
7. Record the customer who asked for this in the docket so future
   audits know why a specific backend was added.

---

## 8. Cross-links

* SOT for all key types + rotation procedures:
  [`docs/SECURITY_KEYS.md`](SECURITY_KEYS.md).
* Production Vault backend:
  [`apps/migration_cloud/services/hsm_vault.py`](../apps/migration_cloud/services/hsm_vault.py).
* HSM interface scaffold (this doc's target):
  [`apps/migration_cloud/services/audit_root_signing_hsm.py`](../apps/migration_cloud/services/audit_root_signing_hsm.py).
* Audit-event signing dispatcher:
  [`apps/migration_cloud/services/audit_root_signing.py`](../apps/migration_cloud/services/audit_root_signing.py).
* Audit-log architecture:
  [`docs/MIGRATION_CLOUD_AUDIT_LOG.md`](MIGRATION_CLOUD_AUDIT_LOG.md).
