# Security Keys — Rotation & Recovery Runbook

Operator-facing runbook for every secret material on the RunMyCampus
platform. **Audience:** on-call SRE / DevOps with shell access to the
production environment. **Last updated:** v3.32.0, 2026-05-18.

This document is a **runbook**, not a tutorial. Each section answers:
"where does this live, how do I rotate it, how do I recover from
compromise". Every example uses obvious placeholders like
`xxxx-xxxx-xxxx-xxxx` — never paste a real key into this file.

---

## 0. Inventory

| Key / Secret | Purpose | Storage |
|---|---|---|
| `SECRET_KEY` | Django session signing, CSRF tokens, `dumpdata` signatures | Env var (production), `.env.local` (dev) |
| `DJANGO_CRYPTOGRAPHY_KEY` | Fernet key for User legacy hash columns + webhook `secret_ciphertext` (v3.32.0) | Env var |
| `CompanionKeypair` private | X25519 sealed-box decrypt for Companion uploads | Encrypted DB row (per-tenant) |
| `MigrationCloudWebhookSubscription.secret_ciphertext` | HMAC-SHA256 signing for outbound webhook deliveries | DB column (Fernet-wrapped at rest) |
| `MigrationCloudAPIToken.token_hash` | Bearer-token sha256 for partner API access | DB column (sha256 only — plaintext never stored) |

Anything not on this list is either (a) derived (e.g. CSRF token) or
(b) a third-party credential (Stripe, Sentry, SMTP) whose rotation
docs live with that vendor — link them in `docs/INCIDENT_RESPONSE.md`.

---

## 1. `SECRET_KEY`

### Purpose
Django uses `SECRET_KEY` to sign sessions, CSRF tokens, password reset
tokens, and `signing.dumps()` payloads.

### Storage
- **Production:** environment variable on the host (Render / k8s).
- **Dev:** `.env.local` at the repo root (gitignored).

### Generate

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Rotation (zero-downtime)

1. Generate the new value (above).
2. Add it to the runtime as `SECRET_KEY_FALLBACKS` (Django supports a
   list of fallbacks for signature verification of in-flight tokens).
3. Roll the new `SECRET_KEY` to the primary slot across all web
   workers.
4. Wait at least `PASSWORD_RESET_TIMEOUT` (default 3 days) and one
   session lifetime so any in-flight signed payloads expire naturally.
5. Drop the old key from `SECRET_KEY_FALLBACKS`.

### Recovery (compromise)

- Rotate **immediately** using the procedure above but skip the wait.
- Force a logout of every active session:
  `User.objects.update(last_login=timezone.now())` is not enough —
  rotate `SECRET_KEY` and Django will invalidate every existing
  session signature on next request.
- Audit log: confirm the `key rotation` warning was emitted (see §6).

---

## 2. `DJANGO_CRYPTOGRAPHY_KEY`

### Purpose
Fernet key (AES-128-CBC + HMAC-SHA256) used by
`apps.accounts.legacy_hashes.encryption` to encrypt:

- `User.legacy_password_hash` / `legacy_hash_algorithm` /
  `legacy_hash_params` (foreign-vendor hash columns)
- `MigrationCloudWebhookSubscription.secret_ciphertext` (webhook
  signing material, v3.32.0)

### Storage
- **Production:** environment variable.
- **Dev:** falls back to a SECRET_KEY-derived value (see
  `encryption._resolve_fernet_key()`). Production MUST set this
  explicitly.

### Generate

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Output is 44 URL-safe-base64 characters (e.g. `xxxx-xxxx-xxxx-xxxx-...`).

### Rotation (MultiFernet pattern)

The Fernet library supports a `MultiFernet([new, old])` that decrypts
with any key in the list and encrypts with the first. To rotate:

1. Generate the new key (above). Store it alongside the old one
   in a list-typed env var:

   ```
   DJANGO_CRYPTOGRAPHY_KEYS=<INSERT NEW KEY HERE>,<INSERT OLD KEY HERE>
   ```

2. Deploy. `_get_fernet()` builds `MultiFernet([new, old])`. New
   writes encrypt under `new`; old writes still decrypt.

3. Run the backfill script to re-encrypt every legacy hash row + every
   webhook subscription row through the new key:

   ```bash
   python manage.py shell -c "
   from scripts.encrypt_existing_legacy_hashes import rewrap_all
   rewrap_all(force=True)
   "
   ```

   (For webhook secrets: same idea, query
   `MigrationCloudWebhookSubscription.objects.all()` and re-save each
   row — the descriptor encrypts on save under the new primary.)

4. Audit: confirm every `legacy_password_hash` decrypts under the new
   key alone. Drop the old key from the env list.

### Recovery (compromise)

- Compromise of `DJANGO_CRYPTOGRAPHY_KEY` means an attacker who also
  has a DB dump can decrypt every legacy hash + webhook secret.
- Rotate **immediately** using the MultiFernet pattern above.
- Cycle every webhook subscription's secret (each subscriber must
  re-subscribe; see §4).
- The legacy hashes themselves are pre-Argon2 vendor hashes — they
  cannot be "re-protected" once exposed; rely on the v3.29 sunset job
  (`accounts-sunset-stale-legacy-hashes`) to drop them within 12+1
  months.

---

## 3. `CompanionKeypair` private keys

### Purpose
X25519 sealed-box decryption for Companion-extension uploads. Each
tenant has one or more active keypairs; the public key is shipped to
the Companion at install time, and the Companion uses libsodium
sealed-box to encrypt the migration payload so only the platform's
private key can open it.

### Storage
`apps.migration_cloud.companion_receiver.CompanionKeypair` model. The
private key is itself encrypted at rest via the same Fernet wrap as §2
(so rotating `DJANGO_CRYPTOGRAPHY_KEY` covers Companion keys too).

### Generate
Done by the platform on tenant onboarding, via:

```bash
python manage.py shell -c "
from apps.migration_cloud.companion_receiver import rotate_companion_keypair
rotate_companion_keypair(tenant_id=<INSERT TENANT ID>)
"
```

### Rotation (grace-period pattern)

Companion clients cache the public key for ~24h, so a hard cutover
breaks in-flight uploads. The model carries `is_active` + `retired_at`
to allow N keypairs per tenant.

1. Generate a new keypair (above). Mark `is_active=True`.
2. Mark the prior keypair `is_active=False` but DO NOT delete — the
   receiver still tries each active OR within-grace-period key for
   decryption.
3. After 7 days (configurable per tenant), the cron job
   `companion-prune-expired-keypairs` deletes private keys whose
   `retired_at` is older than the grace window.

### Recovery (compromise)

- If a single tenant's private key leaks: rotate that tenant's
  keypair only (above) with a 24-hour grace period instead of 7 days.
- If `DJANGO_CRYPTOGRAPHY_KEY` leaks (which protects ALL Companion
  private keys at rest): rotate `DJANGO_CRYPTOGRAPHY_KEY` per §2,
  THEN rotate every tenant's Companion keypair, THEN force-revoke
  every in-flight upload receipt (`CompanionUploadReceipt.status =
  'revoked-due-to-key-rotation'`).

---

## 4. Webhook subscription secrets

### Purpose
HMAC-SHA256 signing material for outbound webhook deliveries. Each
`MigrationCloudWebhookSubscription` has one secret; subscribers
verify the `X-Migration-Cloud-Signature: sha256=<hex>` header against
their copy.

### Storage
`MigrationCloudWebhookSubscription.secret_ciphertext` (BinaryField,
Fernet-wrapped at rest via `EncryptedBinaryField`, v3.32.0).

`secret_hash` (sha256 of the plaintext secret) is also stored as a
support-flow verification aid — operators can confirm "your secret
hashes to X" without ever holding the secret.

### Generate
Generated at subscription creation time by
`apps.migration_cloud.api.webhooks._generate_secret()`:

```python
plaintext = "whsec_" + secrets.token_urlsafe(32)
```

Returned to the caller **once** in the `POST /webhooks/` response. The
platform never gives it back.

### Rotation

We do not support in-place secret rotation — the partner re-subscribes:

1. Partner calls `DELETE /webhooks/<old_id>/` (sets `active=False`).
2. Partner calls `POST /webhooks/` for a new subscription — receives
   a fresh secret in the response.
3. Partner updates their HMAC verifier to use the new secret.

This avoids the "did the partner update before the rotation took
effect" race that breaks every in-flight delivery.

### Recovery (compromise)

- If a single subscription's secret leaks: delete + recreate (above).
- If many secrets leak at once (e.g. via `DJANGO_CRYPTOGRAPHY_KEY`
  compromise): operator runs the bulk re-issue script (operator-only,
  not yet wired — manual `POST /webhooks/<id>/cycle/` per row works
  for now).
- The platform NEVER stores the plaintext after creation, only the
  Fernet-wrapped ciphertext. So a DB dump alone (without the Fernet
  key) is not sufficient to forge a delivery.

---

## 5. `MigrationCloudAPIToken` scoped tokens

### Purpose
Partner API access tokens (bearer auth, scoped to a fixed action set
like `bundles:read`, `templates:read`, etc.). Each token is presented
as `Authorization: Bearer rmctok_<RAW>`; the platform stores only
`sha256(RAW)`.

### Storage
`MigrationCloudAPIToken.token_hash` (CharField). The RAW plaintext is
never persisted — visible only in the `POST /tokens/` response.

### Generate
Done by `apps.migration_cloud.api.tokens.create_token_view`:

```python
raw = "rmctok_" + secrets.token_urlsafe(40)
row.token_hash = hashlib.sha256(raw.encode()).hexdigest()
```

### Rotation (grace chain)

v3.32.0 added `MigrationCloudAPIToken.rotated_to` (self-FK) +
`grace_until`. To rotate:

1. Partner calls `POST /tokens/<old_id>/rotate/`. Platform creates a
   new row, sets `old.rotated_to = new`, `old.grace_until = now() +
   7d`, returns the new plaintext.
2. Both tokens authenticate during the 7-day window.
3. After `grace_until` elapses, the old token is rejected; partners
   discover any forgotten clients via 401 in their monitoring.

### Recovery (compromise)

- `POST /tokens/<id>/revoke/` sets `revoked_at = now()`. Token
  immediately stops authenticating — no grace.
- Audit log: `api_token_revoked` event with `operator_user_id`,
  `token_id`, `reason`. Never the token plaintext.

---

## 6. Incident response

### Signs of compromise

| Signal | Likely cause |
|---|---|
| Webhook signatures verifying for payloads the platform did not send | `secret_ciphertext` leaked |
| Unauthorized DB writes via API | `MigrationCloudAPIToken` raw value leaked |
| Decrypted legacy hashes in a leaked log | `DJANGO_CRYPTOGRAPHY_KEY` leaked OR raw plaintext logged somewhere it shouldn't be |
| Login bypass | `SECRET_KEY` leaked (session forgery) |

### Immediate-action checklist

1. **Identify** which key was compromised. Cross-reference against the
   inventory in §0.
2. **Rotate** per the relevant section above.
3. **Force-logout / re-auth** every active session if `SECRET_KEY` is
   involved.
4. **Notify** the security operator distribution list with the audit
   log entries — `logger.warning("key rotation", ...)` emits one per
   rotation event with `key_type`, `operator`, `key_version_old`,
   `key_version_new`. Never key material.
5. **Document** in `docs/INCIDENTS/<YYYY-MM-DD>-<slug>.md`.
6. **Run** the post-incident review within 7 days; add any missing
   detection signal to `apps/observability/`.

### Audit log expectations

Every rotation event MUST emit one structured log line:

```python
logger.warning(
    "key rotation",
    extra={
        "key_type": "DJANGO_CRYPTOGRAPHY_KEY",
        "operator": "<INSERT OPERATOR ID>",
        "key_version_old": "<INSERT OLD VERSION SLUG>",
        "key_version_new": "<INSERT NEW VERSION SLUG>",
    },
)
```

Never log key material itself — Fernet keys are 44 base64 chars; a
44-char base64-looking string in the logs is a P0 leak.

---

## 7. Test coverage

- `apps/accounts/tests/test_security_keys_runbook.py` — asserts every
  required section is present in this file and that no example code
  block contains a literal-looking key.
- `apps/accounts/tests/test_legacy_hash_intake.py` — asserts the
  intake helper never logs hash bytes.
- `apps/migration_cloud/tests/test_webhook_secret_encryption.py` —
  asserts the wrap migration is idempotent + the dispatcher HMACs
  match recipient-side verification.

If you change this runbook, also update those tests.

---

## Appendix A — recovery checklist (single page)

```
[ ] Stop the bleed: revoke the compromised key NOW.
[ ] Identify scope: which tables / sessions / partners are affected?
[ ] Rotate per the relevant section above.
[ ] Notify the security distribution list.
[ ] File an incident doc in docs/INCIDENTS/.
[ ] Schedule the post-incident review.
[ ] Update detection: what missing alert would have caught this?
```
