# Education OS Kernel Domain Map

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_KERNEL_MAP_READY`

## Scope

Maps every existing Django app into one of 8 OS layers (Kernel Runtime, Configuration Plane, Relationship Plane, Academic Plane, Commerce Plane, Operations Plane, Intelligence/Extension Plane, Global-Local Edge Plane). For each app: current role, target OS role, dependencies, events emitted/consumed, tenant safety boundary, metadata/config usage, workflow usage, API exposure, test coverage, PWA/offline relevance, stakeholder OS relevance, gaps.

## Sections

### Layer 1 — Kernel Runtime

- platform_runtime — pack/blueprint lifecycle (apply/audit/preview/rollback). Target: OS kernel runtime; consumes events; emits package.applied/.rolledback.
- tenancy — tenant lookup + tenant context propagation. Target: tenant identity kernel.
- accounts — user/account model + session binding. Target: actor/identity primitive.
- schools — School canonical model + soft delete (live_objects manager). Target: canonical core.
- security — permissions + audit + tenant boundary scanner. Target: kernel security service.
- siteconfig — SiteSettings + CountryRegistry + cockpit_payload. Target: kernel config primitive.
- metadata — custom fields + global mapping. Target: kernel metadata service.
- global_registries — immutable global core field registry. Target: kernel universal schema service.
- registries — supporting lookup registries. Target: kernel registry service.
- events — domain event bus + outbox. Target: kernel event service.
- lifecycle — SchoolLifecycleStage + onboarding/offboarding state machine. Target: kernel lifecycle service.

### Layer 2 — Configuration Plane

- setup_studio — onboarding wizard + select_experience_template step. Target: tenant setup OS.
- studio_os — operator control plane + experience fold + 200x polish. Target: operator design OS.
- brand_experience — experience templates + TemplateAssignment + TemplateAuditEvent. Target: experience config.
- runtime_blueprints — blueprint definitions. Target: tenant manifest spec.
- packages — InstalledPackage + PackageChangeLog. Target: package lifecycle ledger.
- policies + policies_rules — runtime policy enforcement. Target: kernel policy service.
- plans_entitlements — plan-to-entitlement mapping. Target: subscription contract.
- locale — localization runtime. Target: locale/region overlay service.
- marketplace — 98-template local-first catalog + monetization manifest. Target: template marketplace.

### Layer 3 — Relationship Plane

- sales — admissions pipeline + lead scoring. Target: CRM admissions engine.
- customers — customer profile primitive. Target: customer entity.
- customersuccess — auto-onboarding + retention. Target: customer success OS.
- communication — omnichannel adapters (email/push/SMS/WhatsApp/Telegram/IVR/USSD contracts). Target: communication OS.
- feedback — Voice-of-Customer loop. Target: feedback router.
- people — guardian/custody relationship graph. Target: relationship graph service.
- student360 — lifecycle timeline + dual-identity profile. Target: student journey graph.
- requests — generic request lifecycle. Target: case/ticket primitive.

### Layer 4 — Academic Plane

- academics — syllabus + homework guard + grading schema. Target: academic engine.
- evals — micro-progress timeline + risk drivers. Target: evaluation engine.
- reports — report card factory + transcript. Target: report engine.
- school_events — calendar + permission slips. Target: events engine.
- dashboard — role-aware dashboards. Target: dashboard composer.

### Layer 5 — Commerce Plane

- finance — invoices + wallet limits + permission-to-pay. Target: ledger primitive.
- billing — usage metering + plan link. Target: billing engine.
- payroll — salary + reimbursement ledger. Target: payroll engine.
- integrations_marketplace — third-party integration installs. Target: integration store.

### Layer 6 — Operations Plane

- schoolops — TransportAssignment + HostelAssignment + MealPlanBalance + asset QR loop. Target: campus operations engine.
- sync_engine — Tenant Manifest compiler + edge sync + offline queue + P2P. Target: edge/offline kernel.
- migration_cloud — AI auto-migration + visual data cleanup. Target: migration OS.
- observability — telemetry packets + edge heartbeat. Target: observability engine.
- compliance — DSAR + compliance heartbeat. Target: compliance engine.

### Layer 7 — Intelligence and Extension Plane

- apicenter — ai_helpers boundary + AI safety (baseline 0). Target: AI gateway primitive.
- api — REST API surface. Target: external API.
- automation — workflow engine. Target: tenant automation runtime.
- orchestration — async job orchestration + hold queue. Target: workflow orchestrator.
- analytics — analytics primitives. Target: analytics engine.
- social_media — social adapter contracts. Target: social bridge.
- interop — student/teacher transfer envelopes + self-healing integration sandbox. Target: interoperability kernel.

### Layer 8 — Global-Local Edge Plane

- service-worker.js (131KB) + rmc-service-worker-registration.js + offline-queue-client + conflicts UI. Target: PWA shell.
- sync_engine — manifest compiler + low-bandwidth budget + shared-device profile contract. Target: edge runtime.
- siteconfig.country_registry + 250 ISO2 profiles + 25 LocalExperienceProfile + 75-template local-first. Target: global-local overlay.
- compliance — data residency policy contract. Target: sovereignty service.

## Repo evidence (anchor paths)

- `apps/platform_runtime/`
- `apps/tenancy/`
- `apps/accounts/`
- `apps/schools/`
- `apps/security/`
- `apps/siteconfig/`
- `apps/metadata/`
- `apps/global_registries/`
- `apps/events/`
- `apps/lifecycle/`
- `apps/setup_studio/`
- `apps/studio_os/`
- `apps/brand_experience/`
- `apps/marketplace/`
- `apps/sales/`
- `apps/customersuccess/`
- `apps/communication/`
- `apps/people/`
- `apps/student360/`
- `apps/academics/`
- `apps/evals/`
- `apps/reports/`
- `apps/finance/`
- `apps/billing/`
- `apps/payroll/`
- `apps/schoolops/`
- `apps/sync_engine/`
- `apps/migration_cloud/`
- `apps/observability/`
- `apps/compliance/`
- `apps/apicenter/`
- `apps/automation/`
- `apps/orchestration/`
- `apps/interop/`
- `static/js/service-worker.js`

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
