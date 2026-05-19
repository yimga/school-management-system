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

### Per-tenant scoping (v3.34.0)

**Keypairs are scoped per tenant via `MigrationCloudCompanionKeypair.tenant`.**
A single-tenant key leak no longer blasts radius across the platform:

* `services.companion_keypair.ensure_active_keypair(tenant)` mints
  one active row per tenant.
* `services.companion_keypair.rotate_active_keypair(tenant)` rotates
  THAT tenant only — Tenant B's keypair is untouched.
* `services.companion_keypair.decrypt_with_active_or_versioned(tenant, ciphertext, key_version=…)`
  filters by `tenant_id` first, so a cross-tenant ciphertext surfaces
  as a libsodium `CryptoError` instead of plaintext.
* The DB-level partial unique constraint
  `uniq_active_keypair_per_tenant` (scoped to `(tenant, is_active=True)`)
  enforces one-active-per-tenant; `uniq_keypair_version_per_tenant`
  enforces per-tenant monotonic versioning.
* `companion_server_pubkey_view` (`GET /companion/server-pubkey/`)
  resolves the caller's `request.tenant` and returns ONLY that
  tenant's public key. Anonymous + no-tenant callers receive
  `400 no_tenant`.
* `CompanionKeypairRotateView` (`POST /companion/keypair/rotate/`) is
  staff-only AND tenant-scoped: a staff user can only rotate the
  keypair of the tenant they are currently bound to via session.
* `CompanionDecryptHookView` cross-checks `bundle.school ==
  request.tenant` before decrypt; mismatched tenants return
  `403 tenant_mismatch`.

**Blast radius**: limited to the affected tenant. Other tenants'
in-flight Companion uploads remain valid.

### Storage
`apps.migration_cloud.models.MigrationCloudCompanionKeypair` model
(per-tenant FK to `schools.School`). The private key is itself
encrypted at rest via the same Fernet wrap as §2 (so rotating
`DJANGO_CRYPTOGRAPHY_KEY` covers Companion keys too).

### Generate
Done by the platform on tenant onboarding, via:

```bash
python manage.py shell -c "
from apps.schools.models import School
from apps.migration_cloud.services.companion_keypair import ensure_active_keypair
ensure_active_keypair(School.objects.get(pk='<INSERT TENANT PK>'))
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
`MigrationCloudWebhookSubscription` has one secret; subscribers verify
the `X-RunMyCampus-Signature: sha256=<hex>` header (or the legacy
`X-Migration-Cloud-Signature` header during the dual-emit window —
they are byte-identical) against their copy.

### Header family migration (v3.35.0)

The outbound dispatcher emits both header families during the
2026-05-18 → 2026-08-18 window. Customer migration timeline,
backwards-compat notes, and operator escape-hatch flag are documented
in [`docs/WEBHOOK_HEADER_MIGRATION_2026.md`](WEBHOOK_HEADER_MIGRATION_2026.md).
Operators flip `MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=False` to suppress
the legacy family once all downstream receivers have migrated.

### Customer integration path (v3.34.0+)

Customers verify inbound webhooks using the **official packaged SDKs**:

* Python: `pip install runmycampus-webhook-verifier` — source at
  [`packages/runmycampus-webhook-verifier-py/`](../packages/runmycampus-webhook-verifier-py/)
* JS / TS: `npm install @runmycampus/webhook-verifier` — source at
  [`packages/runmycampus-webhook-verifier-js/`](../packages/runmycampus-webhook-verifier-js/)

Both packages:
* Use constant-time HMAC compare (`hmac.compare_digest` /
  `crypto.timingSafeEqual`).
* Enforce optional clock-skew window (default 300s) via the
  `X-RunMyCampus-Timestamp` header for replay defense.
* Reject unsupported signature prefixes (`sha512=`, etc.) — fail
  closed rather than silently accept anything claiming to be signed.
* Are byte-for-byte interoperable (shared canonical-JSON fixture
  asserts identical output across Python + JS).
* Ship with zero third-party runtime dependencies — installable in
  air-gapped environments.

The vendored single-file copies at
`apps/migration_cloud/api/webhook_verifier_sdk.py` and
`apps/migration_cloud/api/static/runmycampus_webhook_verifier.js` are
preserved through v4.0.0 for customers who cannot reach PyPI / npm,
but are **deprecated** — new integrations should use the packaged
SDKs.

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

## Automated Rotation Tooling

v3.33.0 ships first-class tooling around `DJANGO_CRYPTOGRAPHY_KEYS`
MultiFernet rotation. The operator stays in the loop on every key
migration — auto-rotate is intentionally NOT wired to the beat.

### Management command

```
python manage.py rotate_encryption_keys                  # dry-run (default)
python manage.py rotate_encryption_keys --apply          # actually rewrap
python manage.py rotate_encryption_keys --model accounts.User
python manage.py rotate_encryption_keys --verify-orphans # read-only orphan scan
```

Behavior:

* Default mode is **dry-run** — scans every Fernet-wrapped column,
  exercises the decrypt path under the MultiFernet, but never writes.
  Surfaces which rows would be re-encrypted under the newest key.
* `--apply` re-encrypts and commits. Per-row `transaction.atomic()`
  savepoint so a failure on row 47 doesn't poison rows 1-46.
* `--model app_label.ModelName` scopes the run to a single table.
* `--verify-orphans` runs the read-only audit (next section).
* **Idempotent** — a second `--apply` run finds zero rows to rewrap.

The wrapped fields auto-discovered: every `EncryptedCharField` /
`EncryptedJSONField` / `EncryptedBinaryField` declared on any model in
the project (v3.33.0: User legacy_* columns + Webhook
`secret_ciphertext` + Companion keypair private bytes).

### Beat schedule

```
CELERY_BEAT_SCHEDULE["accounts-key-rotation-monthly"]
  # task: accounts.audit_encryption_key_orphans
  # crontab(hour=4, minute=0, day_of_month="1")    # 1st of month 04:00 UTC
```

This entry is **read-only**: it calls
`apps.accounts.legacy_hashes.key_rotation.verify_no_orphan_ciphertexts`
and emails the operator distribution list when any orphan rows are
found. It does NOT auto-rotate.

### Audit log path

```
logs/key_rotation_<utc_iso>.jsonl
```

One JSONL line per row + one summary line per run. Each line contains
counts + per-row booleans only — NEVER ciphertext, NEVER plaintext,
NEVER key bytes themselves. Verify with:

```bash
# Count rewrapped vs skipped rows:
jq -r '.event' logs/key_rotation_*.jsonl | sort | uniq -c
```

### Recommended rotation procedure

1. Set `DJANGO_CRYPTOGRAPHY_KEYS = ["<INSERT NEW KEY HERE>", "<INSERT OLD KEY HERE>"]` in env.
2. Deploy. `_get_fernet()` builds `MultiFernet([new, old])`; new
   writes encrypt under `<new>`, old writes still decrypt.
3. `python manage.py rotate_encryption_keys` (dry-run) — verify the
   row count is non-zero (else nothing to do) and zero failures.
4. `python manage.py rotate_encryption_keys --apply` — commits.
5. `python manage.py rotate_encryption_keys --verify-orphans` — confirms
   every row decrypts under the active keys.
6. Once the audit log shows zero rewrapped on a fresh run, drop
   `<INSERT OLD KEY HERE>` from `DJANGO_CRYPTOGRAPHY_KEYS` and redeploy.

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
- `apps/accounts/legacy_hashes/tests/test_key_rotation_v3_33.py` —
  asserts the v3.33.0 MultiFernet rotation tooling: dry-run does not
  write, `--apply` re-encrypts under the newest key, the orphan
  scanner finds zero on a clean DB, and the rotation audit log writes
  counts but NEVER key material (no 44-char base64 fragments in any
  emitted record).

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

---

## Cross-System Trust Anchors

*Added v3.33.0 — single-page map of every key / secret type on the
platform. Use this section as a decision table when triaging a
compromise.*

The trust topology is a layered graph: a leak in one anchor cascades
into the anchors that depend on it. The table below covers (a) where
each anchor lives, (b) who is authorized to rotate it, (c) blast
radius if it is compromised, (d) the recovery path.

| Anchor | (a) Storage | (b) Rotator | (c) Blast radius | (d) Recovery path |
|---|---|---|---|---|
| `SECRET_KEY` | Env var (prod), `.env.local` (dev) | SRE on-call | Session forgery → login bypass platform-wide; CSRF token forgery; signed-URL forgery | §1 rotation with `SECRET_KEY_FALLBACKS`; wait one session lifetime; drop old. Force-rotate immediately on compromise. |
| `DJANGO_CRYPTOGRAPHY_KEYS` (list) | Env var | SRE on-call | Decrypt every legacy hash + webhook secret + CompanionKeypair private bytes in a DB dump | §2 MultiFernet rotation; re-encrypt every wrapped column; cycle every webhook secret + Companion keypair (cascade). |
| `CompanionKeypair` private bytes | DB row (Fernet-wrapped via `DJANGO_CRYPTOGRAPHY_KEYS`) | Staff via `CompanionKeypairRotateView` (POST `/companion/keypair/rotate/`) | Decrypt every in-flight + at-rest Companion ciphertext blob for the affected key version | §3 grace-period rotation; force-revoke in-flight `CompanionUploadReceipt` rows on compromise; revoke MAA where vendor data was leaked downstream. |
| `MigrationCloudWebhookSubscription.secret_ciphertext` | DB column (Fernet-wrapped at rest) | Partner (delete + recreate); operator can force-cycle | Forge inbound webhook payloads for the affected subscriber; replay-attack their downstream | §4 delete + recreate. On mass compromise (Fernet key leak), bulk re-issue per row. |
| `MigrationCloudAPIToken.token_hash` | DB column (sha256 only — plaintext never persisted) | Partner via rotate flow; operator via revoke | API-level access in the scope of the leaked token (e.g. `bundles:write`); cross-tenant access is fenced by `tenant_scope` FK | §5 7-day grace rotation OR immediate revoke; partner self-discovers forgotten clients via 401 monitoring. |
| MAA signature material (signature_text + signature_text_sha256) | DB row (`MigrationAuthorizationAgreement`) | N/A — append-only (operator may revoke an MAA, not edit it) | Audit-trail integrity. The fingerprint is one-way; a leak reveals NO secrets, but a forged signature_text without matching sha256 fails the audit invariant | New revocation row + new MAA; investigate which DB user wrote the divergent row. |
| (Reference) Third-party secrets — Stripe, Sentry, SMTP | Vendor-managed | Vendor consoles + RunMyCampus on-call | Per-vendor (see `docs/INCIDENT_RESPONSE.md` for vendor-specific runbooks) | Vendor-specific. Not in scope for this runbook. |

### Cross-anchor cascade map

When `DJANGO_CRYPTOGRAPHY_KEYS` is compromised, the cascade is:

```
DJANGO_CRYPTOGRAPHY_KEYS leak
    ├── User.legacy_password_hash decrypted
    ├── MigrationCloudWebhookSubscription.secret_ciphertext decrypted
    │       └── Every active subscription must be re-issued
    └── CompanionKeypair private bytes decrypted
            └── Every CompanionCiphertextBlob can be decrypted
                    └── Every CompanionUploadReceipt must be force-revoked
                            └── Every MAA covering an affected receipt is reviewed
```

When `SECRET_KEY` is compromised, the cascade is:

```
SECRET_KEY leak
    ├── Every active Django session forgeable
    ├── Every CSRF token forgeable
    ├── Every signed URL forgeable
    └── Every "dumpdata" signature forgeable
```

### Compliance-doc cross-links

These anchors are referenced by the following compliance documents.
Keep them in sync when rotating:

- **`docs/DSAR_RUNBOOK.md`** — references `apps.policies.dlp` (which
  consults `FieldCatalogEntry.sensitivity_tier`; rotation does not
  affect the catalog, but a Fernet rotation requires re-encrypting
  the wrapped fields). DSAR exports MUST log via
  `PolicyDecisionLog` — see §12 of the DSAR runbook.
- **`docs/DPA_TEMPLATE.md`** — §4.3 (Security) and §4.6 (Breach
  Notification) reference the rotation procedures defined here.
  When rotating, audit-log the event per §6 of this runbook so the
  72-hour breach-notification clock is documented.
- **`docs/SECURITY.md`** — high-level technical and organizational
  measures (TOMs) map; this file is the operational drilldown.

### Operator decision tree

```
Compromise reported
    │
    ├── Is the anchor in our control? (vs. third-party)
    │   ├── Yes  → continue
    │   └── No   → vendor runbook in docs/INCIDENT_RESPONSE.md
    │
    ├── Identify the anchor (§§ 1–5)
    │
    ├── Does it cascade?
    │   ├── DJANGO_CRYPTOGRAPHY_KEYS → cascade map above
    │   ├── SECRET_KEY                → cascade map above
    │   └── Others                    → scoped to that anchor
    │
    ├── Execute the §-specific recovery path
    │
    ├── Notify per DPA §4.6 (72-hour clock)
    │
    └── Post-incident review within 7 days
```

---

## 7. Internal Fernet Shim Migration Plan (v3.34.0+)

### Why this section exists

`apps/accounts/legacy_hashes/encryption.py` ships **two** backends and
auto-selects between them at import time:

1. **Upstream `django-cryptography` 1.x.** Used when the upstream
   package is installed AND its `django.utils.baseconv` dependency
   resolves (i.e. when we're on Django <5 OR upstream has shipped
   1.2+). This is the long-term target.
2. **Internal Fernet shim.** Pure-stdlib AES-128-CBC + HMAC-SHA256,
   binary-compatible with `cryptography.fernet.Fernet`. Used when
   the upstream package is unimportable under Django 5 (the present
   day). Same crypto strength, but maintained by us.

Today the selector reports `current_backend_name() == "internal_fernet_shim"`.
We are watching upstream for a Django-5-compatible release; see
`docs/UPSTREAM_WATCH.md` § 1 for the polling protocol and
`scripts/check_django_cryptography_compat.py` for the watch script.

### When django-cryptography 1.2+ lands

The transition is **transparent at the data layer** — Fernet
ciphertexts produced under the shim decrypt cleanly under upstream,
and vice versa, because both implementations use the same MultiFernet
keyset (`settings.DJANGO_CRYPTOGRAPHY_KEYS`). The migration is purely
a backend identifier change.

### Procedure

1. Verify the candidate release per `docs/UPSTREAM_WATCH.md` § 1.
2. Bump `requirements.txt`:
   ```
   django-cryptography==1.2.0
   ```
3. After deploy, `current_backend_name()` returns
   `"django_cryptography_1_2_plus"`. Confirm:
   ```python
   python manage.py shell -c "from apps.accounts.legacy_hashes.encryption import current_backend_name; print(current_backend_name())"
   ```
4. **No data migration is required for new writes.** New
   ciphertext rows produced under the upstream backend are byte-
   compatible with shim-decryption (transparent fallback).
5. **For existing ciphertexts:** they continue to decrypt under
   upstream without re-encryption. Optionally schedule a sweep
   re-encrypt under upstream on next write:
   ```bash
   python manage.py rotate_encryption_keys --apply --backend-only
   ```
   The `--backend-only` flag (to be added in v3.35) tags the
   ciphertext header with the new backend identifier so audit logs
   can confirm 100% migration.
6. Update the audit-log entry in `key_rotation.py`'s
   `KEY_ROTATION_LOG` to note the backend transition.

### Rollback

If upstream 1.2.0 turns out to have a regression we missed in
verification:

1. Revert `requirements.txt` to the prior `django-cryptography`
   pin (or remove the upstream dep, since the shim has zero
   third-party deps).
2. Redeploy. `current_backend_name()` reverts to
   `"internal_fernet_shim"` automatically — no code changes
   required.
3. Existing ciphertexts that were written under upstream during the
   forward-window remain decryptable under the shim (binary
   compatibility).

---

## Per-vendor legacy-hash coverage (v3.34.0 cross-link)

The "password last set" timestamp that anchors the 12-month sunset
clock is vendor-specific. The full strictness matrix lives in
[`apps/accounts/legacy_hashes/VENDOR_COVERAGE.md`](../apps/accounts/legacy_hashes/VENDOR_COVERAGE.md);
the short version:

| Vendor | Strictness | Notes |
|---|---|---|
| PowerSchool | YES (strict) | `Users.PasswordChanged` column |
| Blackbaud | PARTIAL | `user-modified-time` approximation |
| Veracross | PARTIAL | `pwd_last_changed_dt` per-tenant opt-in; `Last_Modified` fallback |
| Alma | YES (strict) | `passwordUpdatedAt`; `updatedAt` / `createdAt` fallbacks |
| FACTS | NO (write-blocked) | See `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` |
| Skyward | NO (write-blocked) | See `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` |

**FACTS + Skyward write-path counsel docket** —
[`docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md`](FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md)
documents why those write paths remain blocked in v3.34.0
(CFAA / DMCA § 1201 / state-level computer-trespass / *Power
Ventures v. Facebook* / *Sony Betamax*) and lists the
pre-conditions external counsel must sign off on before any
write path is unblocked. Engineering MUST NOT introduce a
feature flag (even default-off) as a workaround; the code stubs
remain literal `// honest-stub:` until sign-off is filed.

---
