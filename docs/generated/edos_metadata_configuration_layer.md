# EdOS Metadata-Driven Configuration Layer

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_METADATA_LAYER_READY`

## Scope

Audits and contracts the metadata layer that absorbs all tenant variance while leaving canonical core models stable. Custom fields, layouts, forms, validation overlays, terminology, report templates, dashboard blocks, workflow rules, regional compliance maps, payment rail configs, template assignments, tenant manifest exports, PWA offline sync policies, stakeholder OS configs, micro-friction toggles, global-local adapter settings, right-to-disconnect rules, split-family routing rules, low-connectivity defaults — ALL metadata, NOT model changes.

## Sections

### Canonical core (STABLE — no schema churn this batch)

- Tenant (apps.tenancy.Tenant)
- User/Account (apps.accounts.User)
- School (apps.schools.School with live_objects manager)
- Student/Person (apps.people.Person + apps.student360.StudentProfile)
- Enrollment + Class/Section (apps.academics)
- Invoice/Payment (apps.finance + apps.billing)
- AuditEvent (apps.security + apps.events)
- Permission (apps.accounts + apps.security)
- WorkflowEvent (apps.events + apps.orchestration)
- Route/Surface (config.tenant_urls + config.urls)
- Guardian/Custody (apps.people)
- Asset (apps.schoolops)
- Message (apps.communication)
- SyncEvent (apps.sync_engine)
- Manifest (apps.runtime_blueprints + apps.platform_runtime.pack_contract)

### Dynamic metadata (tenant variance lives HERE)

- Custom fields → apps.metadata.CustomFieldDefinition with global_field_mapping required for transfer/reporting/analytics participation
- Local terminology → apps.locale + apps.siteconfig.CountryRegistry.cockpit_payload.marketing_voice / mv_per_page_json
- Layouts/forms/validation overlays → apps.brand_experience experience templates + 98-template marketplace
- Report templates → apps.reports template registry
- Dashboard blocks → apps.dashboard block composer
- Workflow rules → apps.automation + apps.orchestration policy bundles
- Payment rail configuration → apps.finance.regional_payment_profiles (250 ISO2 entries) + PSP rail registry
- Regional compliance maps → apps.compliance.policy_map + apps.siteconfig data residency policy
- Tenant manifest export → apps.sync_engine Tenant Manifest compiler + signature/checksum
- Local-first template assignments → apps.brand_experience.models_template.TemplateAssignment + TemplateAuditEvent (append-only)
- PWA offline sync policies → apps.sync_engine.offline_queue + service-worker.js cache strategy
- Stakeholder OS configurations → apps.siteconfig per-stakeholder visibility profile
- Global-local micro-solution adapters → LATAM/Africa/APAC/Europe/MENA adapter registries (Phase 19)
- Right-to-disconnect rules → apps.communication.availability_guard config
- Split-family routing rules → apps.people custody graph + apps.communication multi-custodian router
- Low-connectivity defaults → CountryRegistry.cockpit_payload.low_bandwidth_class per region

### Governance rules

- Core canonical models stay stable — no migrations in this batch.
- Tenant-specific variance MUST go into metadata/config — operator can audit every change.
- Operator global requirements (CSP, MFA enforcement, audit hash policy) are operator-only — tenant cannot override.
- Every config change is audited via apps.security.AuditEvent or apps.brand_experience.TemplateAuditEvent (append-only, HMAC-SHA512 signed).
- Rollback is supported via apps.platform_runtime.pack_rollback + apps.packages.PackageChangeLog.
- Config that needs edge/offline parity is included in the Tenant Manifest (signature-verified before edge apply).

## Repo evidence (anchor paths)

- `apps/metadata/`
- `apps/siteconfig/country_registry.py`
- `apps/brand_experience/models_template.py`
- `apps/marketplace/`
- `apps/platform_runtime/pack_contract.py`
- `apps/runtime_blueprints/`
- `apps/finance/regional_payment_profiles.py`
- `apps/sync_engine/`
- `apps/automation/`
- `apps/orchestration/`

## Tests

- `apps/metadata/tests/test_edos_metadata_layer_contract.py`
- `apps/siteconfig/tests/test_edos_tenant_config_audit_chain.py`
- `apps/brand_experience/tests/test_edos_template_assignment_metadata.py`

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
