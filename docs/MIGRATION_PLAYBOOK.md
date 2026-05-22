# Migration Playbook

> Single operator entry point for everything migration-related. Maintained at `docs/MIGRATION_PLAYBOOK.md`.
> Last refreshed: 2026-05-22 (Wave L5 — Migration auto-launch).

This is an INDEX document. It bundles the dockets, runbooks, and SOPs that already live across `docs/` so an on-call operator doesn't have to hunt.

## The lifecycle

For a single end-to-end view of any school's state across creation → onboarding → operation → migration → offboarding, use:

- Operator: `/super/lifecycle/<uuid:school_id>/` — append-only timeline (Wave L1)
- Tenant: `/portal/migration/status/` — public per-tenant view (Wave L5)

The lifecycle app (`apps/lifecycle/`) is the spine. `SchoolLifecycleStage` is the single timeline; `services_migration.ensure_draft_migration_bundle()` is the auto-launch hook.

## Auto-launch on school creation

When the wizard (or bulk creator, or clone API) populates `school.settings['migration_intent']`, the post_save signal in `apps.lifecycle.signals` automatically drafts a `MigrationBundle` with status=PENDING. The school lands on `/portal/migration/status/` with an active bundle from day one — no operator hunt for the wizard.

`migration_intent` shape:

```json
{
  "vendor": "powerschool",
  "intake_method": "file_upload",
  "expected_students": 1200,
  "label": "Fall 2026 cutover"
}
```

## Reference docs (canonical)

| Topic | File | Purpose |
|---|---|---|
| Companion-extension architecture | `docs/COMPANION_SIBLINGS.md` | Why extraction lives in the operator's authenticated browser |
| Companion handshake + canonical CSV | `docs/COMPANION_SIBLINGS_HANDSHAKE_AND_CSV_INGEST.md` | Tauri/Docker boundary |
| Per-vendor coverage matrix | `apps/accounts/legacy_hashes/VENDOR_COVERAGE.md` | What's read-supported vs counsel-blocked |
| Webhook verification (customer SDK) | `apps/migration_cloud/api/static/WEBHOOK_VERIFICATION.md` | Customer integration |
| Audit log (tamper-evident) | `docs/MIGRATION_CLOUD_AUDIT_LOG.md` | Hash chain + retention |
| Data retention | `docs/MIGRATION_CLOUD_DATA_RETENTION.md` | FERPA 7-year |
| Security keys | `docs/SECURITY_KEYS.md` | Rotation runbook |
| DSAR | `docs/DSAR_RUNBOOK.md` | 30-day SLA |
| MAA v2.0 promotion | `docs/MAA_V2_PROMOTION_CHECKLIST.md` | Counsel-pending flip |
| FACTS / Skyward write counsel | `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` | Open docket |
| Observability metrics | `docs/OBSERVABILITY_METRICS.md` | Prometheus / StatsD bridge |
| Upstream watch | `docs/UPSTREAM_WATCH.md` | django-cryptography compat |
| Signed-release procedure | `docs/COMPANION_SIBLINGS_SIGNED_RELEASE.md` | Apple/Win/Cosign |
| Tenant offboarding | `docs/TENANT_OFFBOARDING.md` | Operator + school-admin journeys |

## Operator dashboards

| URL | What |
|---|---|
| `/super/migration/health/` | 6-panel ops dashboard (webhooks, MAA, companion, keypairs, sunsets, baselines) |
| `/super/migration/command-center/` | 8-card situational awareness (v3.40+) |
| `/super/migration/audit/` | Audit-event log |
| `/super/migration/audit/export/` | NDJSON export (verify_chain=1 supported) |
| `/super/migration/operator/tokens/` | API token mint / rotate |
| `/super/migration/operator/webhooks/` | Webhook subscriptions |
| `/super/migration/operator/webhooks/<sub_id>/audit/` | Per-subscription delivery log |
| `/super/migration/maa-v2-promotion/` | v2.0 MAA flip dashboard (counsel-pending) |
| `/super/migration/vendor-write-status/` | FACTS/Skyward write-path counsel surface |
| `/super/migration/dsar/runbook/` | DSAR workflow |
| `/super/migration/smoke/trigger/` | Smoke-test trigger |
| `/super/migration/smoke/history/` | Smoke-test history |

## Counsel-pending dockets

These are externally-blocked items. Do NOT attempt to unblock without explicit counsel sign-off PDF.

- **MAA v2.0 promotion** — flip awaits counsel signoff at `docs/legal/maa_v2_signoff.pdf`. Plumbing is wired; one env-flag flip + remove from draft set.
- **FACTS / Skyward write paths** — `// honest-stub:` markers in `companion-extension/src/vendors/facts.ts` + `skyward.ts`. Read paths (safe-DOM scraping of operator's authenticated directory printouts) are unchanged.
- **HSM bridges** — `aws-kms` / `azure-keyvault` / `hashicorp-vault` / `gcp-kms` are reserved enum values raising `NotImplementedError`. Implement one before any tenant requests it.

## Wave history (most recent)

- **v3.39** (2026-05-19): platform trust — weekly chain verifier, root-key signature, canonical-headers drift gate, Prometheus bridge, signed-release workflows.
- **v3.38** (2026-05-19): operational maturity — MV3 companion scaffold, per-vendor CSV pre-processors, SDK 1.0.0-rc.1, metrics + health dashboard, tamper-evident audit log.
- **v3.37** (2026-05-19): v3.34 deferred closeout — companion popup tenant switcher, SDK accept_legacy, MAA v2.0 dashboard, RMC handshake + canonical CSV, webhook replay.
- **v3.34** (2026-05-18): per-tenant CompanionKeypair, Tauri/Docker siblings, PyPI+npm SDKs, vendor legacy-hash timestamps, MAA v2.0 plumbing.

## When to escalate

- Audit chain integrity broken (`verify_audit_chain` exit code 1) — page security.
- Root-key signature mismatch (`verify_audit_chain --check-root-signature` exit code 2) — page security AND legal.
- Webhook delivery exhausted with no operator replay within 6h — page ops.
- Companion upload receipt missing for >24h after MAA sign — page customer success.
