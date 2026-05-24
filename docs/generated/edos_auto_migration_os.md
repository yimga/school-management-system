# EdOS Zero-Human Auto-Migration Operating System

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_AUTO_MIGRATION_OS_READY`

## Scope

Re-architects migration_cloud + customersuccess around legacy file intake, spreadsheet intake, database backup intake contract, AI field detection, schema confidence scoring, metadata mapping, duplicate detection, data cleanup dashboard, pre-commit quarantine, migration readiness score, tenant setup auto-generation, customer success handoff, human approval gate, rollback posture, no credential leakage, visual row correction, historical grade mapping, ledger mapping, guardian/custody mapping, student transfer envelope generation.

## Sections

### Pipeline stages (10)

- 1. Intake — drag-and-drop Excel/CSV + DB backup contract (PII redaction at intake; source credentials NEVER logged/prompted)
- 2. Source detection — heuristic + AI-assisted (apicenter.ai_helpers gateway only) source system profile
- 3. AI field mapping — confidence score per field; below threshold flagged for human review
- 4. Duplicate detection — fuzzy match on identity hash + email + phone E.164
- 5. Quarantine — pre-commit isolation per tenant_id; rollback-safe
- 6. Visual data cleanup — row-level error highlighting + browser correction + confidence scores
- 7. Migration readiness score — composite (mapping_coverage + duplicate_rate + validation_pass_rate)
- 8. Tenant setup auto-generation — bulk school/class/section creation gated by readiness score threshold
- 9. Customer success handoff — onboarding checklist generation + auto-assign concierge
- 10. Rollback posture — apps.platform_runtime.pack_rollback consumes apps.migration_cloud rollback markers

### AI safety contracts (baseline 0 enforced)

- All AI calls go through apicenter.ai_helpers — gateway boundary scanner baseline 0
- Source credentials redacted at intake — never enter prompts or logs
- Tenant data redaction layer — PII tokens replaced with classes before AI call
- Human approval gate REQUIRED before commit — no fully automated tenant write
- Rollback marker emitted on every commit — pack_rollback can reverse

## Repo evidence (anchor paths)

- `apps/migration_cloud/`
- `apps/customersuccess/`
- `services/ai_helpers.py`
- `apps/platform_runtime/pack_rollback.py`

## Tests

- `apps/migration_cloud/tests/test_edos_auto_migration_pipeline_v2.py`
- `apps/migration_cloud/tests/test_edos_visual_data_cleanup_v2.py`
- `apps/customersuccess/tests/test_edos_auto_onboarding_handoff_v2.py`

## External blockers (deferred — repo cannot fix)

- live PSP settlement reconciliation per corridor
- SOC2 Type II PDF
- MoE / Ministry of Education per-country live integrations
- WhatsApp Business platform Meta verification
- USSD telecom partner agreements per country
- native push notification wrapper (Capacitor/Tauri) — deferred until first-100-schools proof
- live LiteLLM API keys on Render
- Render SHA parity live verification
- multi-corridor pilot ingestion
- Postgres RLS enforced in production (current local env is SQLite)

## PWA-first posture

PWA is the launch mobile strategy. Native iOS/Android apps are explicitly DEFERRED until web core stability + first-100-schools proof + PWA installability proof. Service worker + manifest + IndexedDB + offline queue shipped in prior batches; this re-architecture preserves and consumes that infrastructure rather than forking.

## Honesty notes

- Repo-scope contracts only — no live vendor integration claims.
- Existing canonical models preserved; metadata layer absorbs tenant variance per architecture correction.
- External blockers listed above remain unchanged by batch 1489.
