# Migration Cloud — first-school UAT runbook (v3.40.0, 2026-05-19)

This is the playbook the operator runs to validate that Migration Cloud
is "ready to be used" on a brand-new tenant. It is the gate behind every
"yes, ship it to the first paying school" decision. **Read it
end-to-end before you touch a real customer's data.**

The runbook is paired with the management command
`python manage.py migration_cloud_smoke` (synthetic-tenant version of
the same flow) and the nightly Celery beat
`migration-cloud-smoke-nightly` (dry-run only, kill-switched off in
prod). Together they form the three-layer trust contract:

1. **Synthetic smoke** — automated, runs nightly in dev/staging.
2. **First-school UAT** — manual, follows this runbook.
3. **Operator vigilance** — ongoing, see § 7.

---

## 1. Pre-flight checklist (must be 100% green before § 2)

| # | Check                                                                                                       | How to verify                                                                              |
| - | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| 1 | `AUTHENTICATION_BACKENDS[0] == "apps.accounts.auth_backends_legacy.LegacyHashUpgradeBackend"`               | `python -c "from django.conf import settings; print(settings.AUTHENTICATION_BACKENDS[0])"` |
| 2 | MAA v1.0 counsel-blessed; `MIGRATION_CLOUD_MAA_DEFAULT_VERSION == "v1.0"`                                   | grep `settings.py` + `services/maa_text.py::AGREEMENT_VERSION_CURRENT`                     |
| 3 | 23 canonical domains hash-locked                                                                            | `python scripts/scan_companion_canonical_headers_drift.py --strict`                        |
| 4 | Latest signed release verified offline                                                                      | `bash companion-tauri/scripts/verify_signed_build.sh <artifact>` (see Agent 5 docs)        |
| 5 | Audit-root signing backend chosen                                                                           | `MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND` env: `local-env-key` (default) or `hashicorp-vault`|
| 6 | Audit signing key configured (recommended)                                                                  | `MIGRATION_CLOUD_AUDIT_SIGNING_KEY` env present and ≥ 32 random bytes (base64-encoded)     |
| 7 | Webhook verifier SDK 1.0.0-rc.1 published                                                                   | `pip show runmycampus-webhook-verifier` + `npm view @runmycampus/webhook-verifier`         |
| 8 | Companion extension signed PKG / DMG / Docker images available                                              | See `docs/COMPANION_SIBLINGS_SIGNED_RELEASE.md`                                            |
| 9 | All 9 zero-tolerance scanner baselines `0`                                                                  | `python scripts/check_documented_baselines.py`                                             |
|10 | DB migrations all applied (no pending leaves)                                                               | `python manage.py makemigrations --dry-run --check`                                        |
|11 | Service worker version monotonic                                                                            | `python scripts/verify_service_worker_version.py --check-monotonic`                        |
|12 | Operator alert email configured                                                                             | `MIGRATION_CLOUD_AUDIT_OPS_EMAIL` + `MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL` env             |

### Environment variables (full list)

The 12 environment variables Migration Cloud reads:

```
MIGRATION_CLOUD_MAA_DEFAULT_VERSION              (default "v1.0")
MIGRATION_CLOUD_AUDIT_OPS_EMAIL                  (default "")
MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN       (default "")
MIGRATION_CLOUD_AUDIT_SIGNING_KEY                (default "")
MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND            (default "local-env-key")
MIGRATION_CLOUD_VAULT_DRY_RUN                    (default "1" — flip to "0" in prod)
MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED            (default "0")
MIGRATION_CLOUD_SMOKE_SYNTHETIC_TENANT           (default "smoke-test-tenant")
MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL             (default "")
MIGRATION_CLOUD_SMOKE_ALLOW_PROD                 (default unset; "1" only when truly intended)
RMC_EMIT_LEGACY_WEBHOOK_HEADERS                  (default "1"; flip "0" after 2026-08-18)
OBSERVABILITY_METRICS_BACKEND                    (default "noop")
```

Any variable that's missing in prod is itself a finding — page on-call
before continuing.

---

## 2. Provision the synthetic tenant

```bash
python manage.py create_tenant \
    --slug smoke-test-tenant \
    --name "Smoke Test Tenant"
```

If your deployment does not have a `create_tenant` command, use the
schema-context manual path:

```python
# manage.py shell
from apps.schools.models import School
School.objects.create(
    slug="smoke-test-tenant",
    name="Smoke Test Tenant",
    is_active=True,
)
```

You should now be able to load `/super/migration/command-center/` and
see the new tenant in the dropdown (if your build includes Agent 6's
command center).

---

## 3. Run the smoke against the synthetic tenant

```bash
python manage.py migration_cloud_smoke \
    --tenant smoke-test-tenant \
    --vendor powerschool \
    --apply \
    --verbose
```

**Expected output:** every section reports `PASS` or `SKIP` (no
`FAIL`). Exit code `0` (all green) or `2` (some optional sections
skipped because a feature isn't shipped in this build). Exit code `1`
means a required section failed — STOP HERE, page on-call, do not
proceed.

The smoke walks 10 sections in order:

```
setup              — env, AUTH_BACKEND[0], MAA active, 23 domains
maa                — sign MAA + persist sha256 + log-leak guard
companion_keypair  — ensure + rotate + fingerprint cross-check
intake             — Agent 7 MigrationIntakeRequest path (optional)
ingest             — POST canonical CSV to /api/v1/migration/bundles/
webhook            — local httpd captures HMAC delivery
sse                — open events stream + verify SSE headers
promotion          — promote_dyna_assignments --apply (idempotent)
audit_chain        — verify_audit_chain --tenant=...
cleanup            — revoke transient token, deactivate webhook sub
```

If you need to skip a section temporarily (e.g. the dev box has no
PyNaCl):

```bash
python manage.py migration_cloud_smoke \
    --tenant smoke-test-tenant \
    --vendor powerschool \
    --apply \
    --skip-section companion_keypair
```

Run the smoke against **all six vendors** before declaring the
synthetic UAT done:

```bash
for v in powerschool blackbaud veracross alma facts skyward; do
    python manage.py migration_cloud_smoke --tenant smoke-test-tenant --vendor "$v" --apply
done
```

(FACTS and Skyward write-paths are still counsel-blocked per
`docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md`; the smoke exercises
read-only ingest and skips the write surface for those two.)

---

## 4. Inspect the Command Center (operator UI)

Open `/super/migration/command-center/`. Confirm:

* All 8 cards render green / nominal.
* The synthetic tenant appears in the recent-activity list.
* Audit chain card shows `clean` status.
* Webhook subscription card shows the smoke's transient sub (now
  deactivated by the cleanup section — that's correct).

If any card is red, drill into it: every card links to a specific
operator dashboard with deeper data.

---

## 5. First-school onboarding (real customer, after § 1–§ 4 green)

This is the procedure you follow for the **first real school**. Do not
skip any step.

1. **Counsel signs MAA v1.0 PDF** — operator emails the PDF to counsel
   for the customer's specific use case (e.g. mid-year transfer from
   PowerSchool). Counsel returns signed PDF; operator stores under
   `docs/legal/maa_signed/<tenant-slug>_v1.0.pdf` (git-ignored;
   actual storage is the secure shared drive per
   `docs/SECURITY_KEYS.md`).
2. **Provision the real tenant** via the standard onboarding flow (NOT
   the synthetic `create_tenant` shortcut — use the operator portal at
   `/super/onboarding/` which goes through proper SSO, billing, MAA
   capture).
3. **Run the smoke against the new tenant in DRY-RUN first**:
   ```bash
   python manage.py migration_cloud_smoke --tenant <real-slug> --vendor <vendor>
   ```
   This validates connectivity and MAA without mutating anything.
4. **Counsel cross-references signed MAA hash** — open
   `/super/migration/maa-audit/?tenant=<slug>`; the displayed
   `signature_text_sha256` MUST match the hash of the signed PDF
   (`shasum -a 256 docs/legal/maa_signed/<slug>_v1.0.pdf`).
5. **Operator pastes the customer's vendor export URL / file** into
   the intake form at `/super/migration/intake/`. The intake row
   begins in `pending`; the operator advances it through
   `extraction-in-progress` → `ingested` via the existing wizard UI.
6. **First ingest is a small subset** (e.g. one grade-level, 25
   students) — never start with a full-school cutover. Confirm the
   bundle lands clean in `/super/migration/bundles/<id>/`.
7. **Re-run the audit chain verifier** with root-signature check
   enabled (per § 6 below). Both the chain and the signatures must
   verify clean.
8. **Schedule full cutover** only after the small-subset bundle
   reconciles cleanly AND the customer's IT-side stakeholder
   countersigns the test report.

---

## 6. Audit chain verification (ongoing)

The audit chain is the legal substrate for every Migration Cloud
action. Verify it on:

* **Every release** — `python manage.py verify_audit_chain --all-tenants`
* **Weekly Celery beat** — `accounts-verify-audit-chain` (Mondays
  02:00 UTC) — already wired.
* **After any backup restore** — `python manage.py verify_audit_chain
  --all-tenants --check-root-signature`. Exit code 2 (chain clean, but
  root-signature mismatch) is the tell-tale of a backup-restore tamper
  attempt.

Exit code map:

```
0   — clean
1   — chain broken (page security + ops immediately)
2   — chain ok, root-signature mismatch (backup restore tamper signal)
```

---

## 7. Companion extension install (per-customer)

1. Operator points the customer's IT contact at the published Chrome
   Web Store / Edge Add-ons / AMO listing (URLs maintained at
   `docs/COMPANION_SIBLINGS.md`).
2. After install, the customer's IT verifies the published version
   matches what's signed by RunMyCampus:
   ```bash
   # On the operator's side:
   sha256sum companion-extension/dist/runmycampus-companion.crx
   # Compare to the published listing's SHA256 (visible in the
   # extension's "About" panel).
   ```
3. If the customer's IT requires Tauri or Docker (locked-down /
   DMZ-only environments), refer them to
   `docs/COMPANION_SIBLINGS.md` for the appliance install path.

---

## 8. Operator vigilance — first 30 days

For each newly-onboarded tenant, the operator monitors the following
signals in Command Center daily for 30 days:

| Signal                              | Threshold for action                                                          |
| ----------------------------------- | ----------------------------------------------------------------------------- |
| Audit chain status                  | Any state ≠ `clean` → page on-call within 1h                                  |
| Webhook delivery success rate       | < 95% over 24h → email customer integration contact                           |
| Webhook delivery latency p99        | > 30s → investigate downstream                                                |
| Token rotation overdue              | > 90 days since last rotate → email scope holder                              |
| API throttle burst                  | Soft-warn header `X-RateLimit-Soft-Warn: 1` ≥ 5x/day → review their integration |
| Legacy-hash decryption volume       | Non-zero after migration cutover + 60 days → investigate (should converge to 0) |
| Failed MAA-sign attempts            | > 0 → review counsel docket; this is suspicious                               |

These are also surfaced as panels in `/super/migration/health/`.

---

## 9. Incident response decision tree

```
Symptom: audit chain BROKEN (verify_audit_chain exit 1)
  → STOP all writes to that tenant immediately (operator UI: deactivate writes)
  → Page security@runmycampus.com
  → Begin forensic preservation: export audit log JSONL, snapshot DB

Symptom: root-signature MISMATCH (verify_audit_chain exit 2, chain clean)
  → Likely backup-restore tamper or signing-key change
  → Confirm signing key has not rotated mid-week
  → Page security + ops
  → Preserve restore source bytes

Symptom: token rotation overdue > 90 days
  → Email scope holder; auto-issue replacement at day 100; force
    rotation at day 120 via `/super/migration/tokens/<id>/rotate/`

Symptom: webhook delivery failure burst > 50 in 24h
  → Disable subscription (the dispatcher does this automatically at
    100 failures); email customer integration contact
  → Re-verify their endpoint's SDK version (1.0.0-rc.1+ required)

Symptom: counsel docket open on FACTS / Skyward write
  → Honor the docket: no write-path code lands until counsel signs
    off. Read paths remain available.

Symptom: smoke command's audit_chain section fails persistently
  → Most likely a synthetic tenant has accumulated corrupted rows
    from a partial test run. Use:
        python manage.py purge_audit_events_pre_approved \
            --tenant smoke-test-tenant \
            --counsel-approval-token=<token> \
            --apply
    (Requires MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN env set.)
```

---

## 10. Sunset / offboarding (when a school leaves RunMyCampus)

When a school migrates AWAY:

1. **Data portability** — operator generates a full canonical-template
   export (24 domains) for the customer. Use
   `/super/migration/export/?tenant=<slug>&format=canonical`.
2. **MAA scope end** — operator marks the MAA agreement `revoked_at =
   now()` via the MAA admin UI. The original signature row is
   PRESERVED for the 7-year FERPA retention window — never deleted.
3. **Key zeroize** — operator rotates the tenant's CompanionKeypair
   via `/super/migration/companion/keypairs/<tenant>/rotate/`, then
   marks the old key inactive. The encrypted private bytes remain in
   the database (for forensic chain-of-custody) but are no longer used.
4. **Audit log retention** — audit events for the offboarded tenant
   remain queryable for 7 years per FERPA. The
   `purge_audit_events_pre_approved` command can purge them earlier
   ONLY with counsel signoff (token in env).
5. **Webhook subscriptions** — deactivate; do not delete.
6. **Scoped API tokens** — revoke all; entries persist (audit trail).
7. **Final confirmation email** — operator sends the customer:
   * The canonical export ZIP
   * The signed MAA PDF (their copy)
   * The audit log JSONL export (read-only forensic record)
   * A signed "migration complete" attestation letter (template at
     `docs/legal/migration_complete_attestation_template.md`)

After offboarding, the tenant slug MUST NOT be re-issued for at least
12 months (avoids any chance of audit-log correlation collision).

---

## Appendix A — quick reference

```bash
# Run the smoke (synthetic)
python manage.py migration_cloud_smoke --tenant smoke-test-tenant --vendor powerschool --apply

# Run the smoke (real tenant, dry-run only)
python manage.py migration_cloud_smoke --tenant <slug> --vendor <vendor>

# Verify audit chain (single tenant)
python manage.py verify_audit_chain --tenant <slug>

# Verify audit chain (all tenants, weekly beat invocation)
python manage.py verify_audit_chain --all-tenants

# Verify audit chain + root-signature
python manage.py verify_audit_chain --tenant <slug> --check-root-signature

# Counsel-approved purge of audit events
python manage.py purge_audit_events_pre_approved --tenant <slug> --counsel-approval-token=<token> --apply

# Promote v3.28 DFV assignments to first-class
python manage.py promote_dyna_assignments --tenant <id> --apply --limit 1000
```

---

## Appendix B — known limitations

* FACTS and Skyward write paths remain `// honest-stub:` per
  `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md`. The smoke
  exercises read-only ingest for those vendors.
* MAA v2.0 is in DRAFT; counsel signoff PDF pending. See
  `docs/MAA_V2_PROMOTION_CHECKLIST.md` for the flip procedure once
  signoff lands.
* HSM signing backends (`aws-kms`/`azure-keyvault`/`gcp-kms`) are
  reserved; only `local-env-key` and `hashicorp-vault` (dry-run by
  default) have working backends in v3.40.0.
* The nightly smoke is **dry-run only** — by design. Production state
  is never perturbed even if the dev kill-switch leaks. To exercise
  the apply path, run the manual smoke per § 3 (operator presence
  required).
