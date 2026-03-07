# Docs roadmap audit — implemented vs not implemented

**Purpose:** Single audit of all roadmaps in the `docs` folder: list each roadmap doc, extract items, and mark each as **Implemented** or **Not implemented** with evidence.

**Generated:** From docs section scan; cross-referenced with codebase and ROADMAP_DUE_TODAY.md.

---

## 1. Roadmap documents found

| Doc | Location | Type |
|-----|----------|------|
| PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT | docs/architecture/ | 5-year horizon + module rollout + backlog |
| REFINEMENT_AND_IMPLEMENTATION_ORDER | docs/architecture/ | Priority 1–4 refinement items |
| section_15_scope_implemented_and_roadmap | docs/architecture/ | Section 15 (360, DynamicField, ledger) |
| ROADMAP_DUE_TODAY | docs/architecture/ | Policy: all due today; status table (authoritative) |
| ROADMAP_AND_OPTIONAL_CLOSURE | docs/architecture/ | Closure of roadmap/optional rows |
| phase7-roadmap | docs/ | Phase 7: QA, URLs, UX, dashboard, integrations |
| PHASE_9_ROADMAP | docs/ | Phase 9: BI, mobile, ML, scheduling, video, payments |
| PHASE7_NICE_TO_HAVE_ROADMAP | docs/ | Nice-to-have: SMS, mobile, homework, discipline, etc. |
| RUNMYCAMPUS_ROADMAP_TASKS | docs/ | Actionable task list (Priorities 1–7 + architecture) |
| RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP | docs/ | Gap analysis + suggested priority order |
| RUNMYCAMPUS_CODEBASE_AUDIT_AND_WORLD_CLASS_ROADMAP | docs/ | Audit Q&A + dashboard/onboarding actions |
| REMAINING_PHASES_EXECUTION_ORDER | docs/architecture/ | Phases 1–24 execution order |
| DONE_WHEN_AND_SCOPED_WORK_LIST | docs/architecture/ | Done-when and scoped work list |
| ROADMAP_TOKEN_SUMMARY | docs/ | One-line token summary (no item list) |

---

## 2. PLATFORM_ROADMAP_5Y (docs/architecture/PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md)

| Item | Implemented? | Evidence / notes |
|------|--------------|-------------------|
| Runtime constitution | Yes | ARCHITECTURE_OVERLAY_AND_RUNTIME_CONSTITUTION.md; request.tenant_runtime |
| Refactor waves 1–8 | Yes | Documented done |
| Tenant-facing Get blueprints (11.2) | Yes | siteconfig:get_blueprints, Admin Panel |
| UX rules audit + list search/filter/export (26.5) | Yes | Students, Invoices, Teachers, Guardians, Evals; FormDraft |
| Control plane maturity (health, SLOs, canary) | Yes | observability SLO dashboard; roadmap_due_today_views CanaryStatusAPI, RPO_RTOConfigAPI |
| Tenant app billing (6.3/29.10) | Yes | record_app_install_for_billing; PlatformLedgerEntry on install |
| Sandbox hardening (1.8) | Yes | CSP + sandbox in sandbox_embed; sandbox_hardening_checklist_1_8.md |
| Parent mobile-first (14.4) | Yes | Viewport in portal_base.html; parent_mobile_first_audit_14_4.md |
| Student 360 UI + transcript (15.1, 26.1) | Yes | student_360_page (tabbed); student_360_export; TranscriptLocalizer |
| Global ledger (15.3) | Yes | PaymentPlan, LedgerAccount, post_*_to_ledger; PlatformLedgerEntry; global_ledger_15_3.md |
| Offline-first + sync (16.5) | Yes | enable_offline_mode; offline_replay_views; sync_delta_api; mobile_api sync_batch |
| Ed-Fi / CEDS (18.x) | Yes | apps/interop/edfi/adapter.py, ceds/adapter.py |
| WebAuthn/Passkeys (29.1) | Yes | apps/accounts/views_passkey.py, UserPasskey |
| Preview/release canary (29.4) | Yes | preview_release_canary.md; workflow_preview_api; canary_tenant feature |
| Government/district (14.5) | Yes | GovernmentAggregatesAPI; government_district_intelligence.md |
| DynamicField (15.2) | Yes | apps/metadata: models, services, admin |
| Metadata module rollout | Yes | Marked Done in doc |
| Government/District module (EMIS) | Partial | GovernmentAggregatesAPI stub; full EMIS = Y4 roadmap |

---

## 3. REFINEMENT_AND_IMPLEMENTATION_ORDER (docs/architecture/REFINEMENT_AND_IMPLEMENTATION_ORDER.md)

| Item | Implemented? | Evidence |
|------|--------------|----------|
| Priority 1: Structured logging, migration rollback, audit export, blueprint versioning, event backbone | Yes | observability middleware; MigrationRun.rollback_*; compliance admin_audit; update_blueprint_bundles; DomainEvent, WebhookDelivery |
| Priority 2: Finance/attendance/comms policy slices | Yes | policy["finance"], ["attendance"], ["communication"] |
| Priority 2: UX rules (list search/filter/export, form autosave) | Yes | Students, Invoices, Teachers, Guardians, Evals; FormDraft |
| Priority 2: Parent mobile-first | Yes | Viewport; parent_mobile_first_audit_14_4.md |
| Priority 2: Design tokens doc | Yes | design_tokens.md |
| Priority 3: Ed-Fi adapter | Yes | apps/interop/edfi/adapter.py |
| Priority 3: CEDS | Yes | apps/interop/ceds/adapter.py |
| Priority 3: WebAuthn/Passkeys | Yes | views_passkey.py, UserPasskey |
| Priority 3: OpenFeature (doc) | Yes | feature_flags.md |
| Priority 4: Student 360 / transcript | Yes | student_360_page; transcript export path; immutable transcript = optional |
| Priority 4: DynamicField | Yes | apps/metadata |
| Priority 4: Global ledger | Yes | PaymentPlan, LedgerAccount, post_*_to_ledger |
| Priority 4: Offline first + sync | Yes | enable_offline_mode; offline APIs |
| Priority 4: Preview/canary | Yes | workflow_preview_api; canary_tenant; RPO_RTO stub |
| Priority 4: Government/district | Yes | GovernmentAggregatesAPI |
| Priority 4: Commercial platform (trials, quote-to-contract) | Not | Scoped; commercial_platform_29_10.md; no self-serve trials/quote-to-contract in code |

---

## 4. section_15_scope_implemented_and_roadmap (docs/architecture/section_15_scope_implemented_and_roadmap.md)

| Item | Implemented? | Evidence |
|------|--------------|----------|
| 15.1 Lifecycle, unified graph, export pack | Yes | student360/services.py; student_360_page, student_360_export |
| 15.1 Full 360 UI (tabs) | Yes | student_360_page.html tabs |
| 15.1 Immutable transcript, cross-year archive | No | Doc says "Roadmap"; no dedicated immutable transcript model or cross-year archive view |
| 15.2 DynamicField (custom attributes, form-driven) | Yes | apps/metadata: models, services, admin |
| 15.3 Multi-currency, VAT/GST, scholarships | Yes | Finance models; tax_engine; global_ledger_15_3.md |
| 15.3 Payment plans, installments | Yes | PaymentPlan, InstallmentPlan, FeeInstallment (finance); global_ledger_15_3.md |
| 15.3 Double-entry ledger | Yes | LedgerAccount; post_invoice_to_ledger, post_payment_to_ledger |

*Note: section_15 doc still labels "Payment plans" and "Double-entry" as Roadmap; codebase has them (global_ledger_15_3.md and finance/billing).*

---

## 5. phase7-roadmap (docs/phase7-roadmap.md)

| Item | Implemented? | Evidence |
|------|--------------|----------|
| QA: regression tests for core workflows | Partial | Various test modules; no single phase7 regression suite documented |
| QA: MFA checks, pen-test checklist | Partial | MFA/passkeys exist; docs/qa.md may exist |
| URL/SEO: breadcrumbs | Yes | templates/partials/breadcrumbs; breadcrumb in control health, rollover |
| URL/SEO: semantic routes, canonical/SEO tags | Partial | Many routes; canonical/SEO not fully audited |
| Widget library (attendance, performance, financial, events, task tracker, timetable, etc.) | Yes | templates/widgets/parent_dashboard_widgets.html, teacher_dashboard_widgets.html, finance_dashboard_widgets.html; phase7 doc marks many ✅ |
| Modular layout (drag-and-drop, UserPreference.dashboard_layout) | Yes | dashboard-layout.js (Sortable.js); DashboardLayout; dashboard_customizer.js (settings) |
| Mobile-first, tap targets, dark/light, RTL | Partial | Viewport; ThemePack; is_rtl in RegionConfig/registries; RTL in policy; full audit optional |
| WhatsApp/Integration credentials, Communication widget | Partial | Integration model; WhatsApp/config varies by deployment |
| docs/qa.md, docs/urls.md, docs/ux.md, docs/automation.md | Unknown | Not verified in this audit |

---

## 6. PHASE_9_ROADMAP (docs/PHASE_9_ROADMAP.md)

| Item | Implemented? | Evidence |
|------|--------------|----------|
| BI & Reporting: executive dashboard, ad-hoc report builder, exports, scheduled emails | Partial | Analytics/dashboard views exist; no dedicated "ad-hoc report builder" or scheduled report emails |
| Mobile: REST/GraphQL API, token/refresh, rate limits, push, offline sync | Partial | REST APIs; JWT; offline sync (sync_batch, delta); push notifications (PushNotificationViewSet); no GraphQL |
| ML Predictions (risk, fee default, performance forecast) | Partial | Early-warning/analytics exist; no full ML model registry or inference endpoints as in Phase 9 spec |
| Advanced Scheduling: timetabling engine, conflict detection, ICS | Partial | Schedule conflicts API; scheduling models; no OR-tools/ILP solver or full timetabling engine |
| Video conferencing: Zoom/Meet, attendance sync, recording links | Partial | Stub or integration points; not full video session creation + attendance sync |
| Payments: subscriptions/instalments, dispute, reconciliation, parent wallet | Partial | PaymentPlan, instalments, ParentWallet exist; dispute handling and payout jobs may be partial |
| Observability: SLOs, audit for ML/scheduling | Partial | SLO dashboard; observability views; ML/scheduling-specific audit not verified |

*Phase 9 is a forward-looking 6–7 week plan; many items are partially present or not yet built.*

---

## 7. PHASE7_NICE_TO_HAVE_ROADMAP (docs/PHASE7_NICE_TO_HAVE_ROADMAP.md)

| Item | Implemented? | Evidence |
|------|--------------|----------|
| SMS/WhatsApp notifications | Partial | Integration model; provider integration varies |
| Mobile app / offline | Yes | Offline mode; sync APIs; PWA/offline documented |
| Homework/assignments (student) | Partial | Cahier de texte / homework modules may exist; not fully verified |
| Discipline/behavior tracking | Partial | discipline_incidents_list; models may exist |
| Multi-school/group | Yes | School model; tenant FK; Option A/B documented |
| Timetable auto-generation | Partial | Scheduling models; no full auto-solver |
| Library/resource management | Partial | feature_registry "library"; no full catalog/loans |
| Video conferencing | Partial | Stub in communication |
| Analytics/BI dashboards | Yes | Analytics views; region timezone/format improvements possible |
| Transport, Hostel, Canteen, Health, Inventory, Biometric | No / Missing | Marked Missing or optional in doc |

---

## 8. RUNMYCAMPUS_ROADMAP_TASKS (docs/RUNMYCAMPUS_ROADMAP_TASKS.md)

| Item | Implemented? | Evidence |
|------|--------------|----------|
| Rosetta Stone API | Yes | apps/api/rosetta_views.py; RosettaStoneConvertAPI, RosettaStoneScalesAPI; normalized_value in conversion |
| normalized_value on grades | Yes | Evaluation.normalized_value (migration 0025); rosetta_stone returns normalized_value |
| Parent Wallet | Yes | apps/finance/models.py ParentWallet, WalletTransaction; portal parent_wallet view; Pay with wallet |
| Attendance CSV export | Partial | Attendance exports may exist; bulk PATCH many not verified |
| MoE/country compliance report presets | Partial | reports/moe_presets.py; government-compliant PDF mentioned |
| Student Passport / vault | Yes | StudentPassport, PassportSchoolInvite; people/models; employer_student_transcript; document_type TRANSCRIPT |
| Self-service tenant signup | No | No public "Sign up my school" → provisioning without super-admin |
| AI narrative feedback | Partial | achievement_event; LLM narrative optional (communication migrations) |
| RTL | Yes | RegionConfig.is_rtl; policies/resolver rtl; portal_base; RUNMYCAMPUS_ROADMAP_TASKS marks [x] |
| UK/British term preset (Michaelmas/Lent/Trinity) | No | No UK preset in doc; education_profile_engine has country packs |
| Nested tenancy | No | No multi-level hierarchy or first-class campus entity |
| Certification/badge expiry alerts | No | Not implemented |
| Employer portal for apprentices | Yes | employer_views (employer_dashboard, employer_student_transcript, etc.); apprentice placement |
| Dual transcript | Partial | transcript_track (ACADEMIC, VOCATIONAL, DUAL); dual_transcript in reports context |
| Redis tenant cache | No | Not implemented |
| Dedicated admin subdomain | Partial | Host routing; admin subdomain not verified |
| Marketing landing | Partial | schools/marketing_views; no single "Start Free Trial" landing verified |
| WhatsApp Business API + push | Partial | Integration; push notifications exist; full server-side WhatsApp not verified |
| Predictive Engine (StudentSignals, risk score) | Partial | Early-warning/analytics; no pgvector/StudentSignals or nightly risk task as specified |
| At-Risk Dashboard, Automated Intervention | Partial | EWS/early warning; no full heat map, Intervention_Logs, Recovery Rate as in doc |
| Executive Dashboard | Partial | Admin/finance dashboards; not unified "Finance + HR + outcomes" single view |
| Locale middleware, 100+ languages, GDPR/FERPA in tenant setup | Partial | Locale/region; compliance; not 100+ languages or full "Compliance Region" in provisioning |
| Schema-based multi-tenancy | Partial | django-tenants in use per RUNMYCAMPUS_CODEBASE_AUDIT; RLS also present |
| API rate limits per tenant | Partial | Rate limiting exists; per-tenant quotas for SaaS billing not verified |
| Promotion/rollover, Intervention tracking, RLS verify, Health records, Audit trail, Help/onboarding, WCAG, Wildcard SSL | Partial | Rollover exists; others vary (audit trail, compliance; WCAG in design_tokens) |

---

## 9. RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP (docs/RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP.md)

This doc summarizes gaps and points to RUNMYCAMPUS_ROADMAP_TASKS and the Cursor plan file. No separate item list; see §8 for task-level status.

---

## 10. RUNMYCAMPUS_CODEBASE_AUDIT_AND_WORLD_CLASS_ROADMAP (docs/RUNMYCAMPUS_CODEBASE_AUDIT_AND_WORLD_CLASS_ROADMAP.md)

| Item | Implemented? | Evidence |
|------|--------------|----------|
| Schema-per-tenant (django-tenants) | Yes | config/settings.py TENANT_APPS, TenantMainMiddleware |
| OnboardingService (validate slug, create schema, seed, first admin) | Partial | Provisioning wizard; full OnboardingService as described not verified |
| Master Table List / migration runner for all tenant schemas | Partial | Migrations exist; "run for all tenant schemas" is deployment concern |
| Dashboard catalog (DashboardTemplate, Configuration Hub) | No | Doc says "Dashboard catalog not yet present"; DashboardWidget exists, no DashboardTemplate |
| School location picker (RegionConfig) in settings | Partial | School.default_region; single "School location" picker in settings not verified |
| FEATURE_GATE_AND_MODULES doc | Unknown | Not verified |
| seed_global_regions, verify_region_coverage | Partial | seed_global_regions command; verify_region_coverage not verified |
| SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING doc | Unknown | Not verified |
| Catalog-backed dropdowns (CatalogChoiceField + allow_other) | Partial | Various dropdowns; pattern not fully audited |
| Configurable admission number generation | Partial | admission_number_mode, pattern; template/strategies may exist |

---

## 11. REMAINING_PHASES_EXECUTION_ORDER (docs/architecture/REMAINING_PHASES_EXECUTION_ORDER.md)

Phases 1–4 and many later phases are marked done in the doc. Items are phase-level; implementation status per phase is documented in the same file. No separate item-by-item table here; see doc for phase checklist.

---

## 12. ROADMAP_DUE_TODAY (docs/architecture/ROADMAP_DUE_TODAY.md)

**Authoritative.** All items in the table are marked **Implemented** (code or stub in apps/api/roadmap_due_today_views.py). See that file for the canonical list and locations.

---

## 13. Summary: not implemented or partial

| Category | Items not implemented or only partial |
|----------|--------------------------------------|
| **Section 15** | Immutable transcript model; dedicated cross-year archive view |
| **Commercial** | Self-serve trials; quote-to-contract; partner tooling (29.10) |
| **Phase 7** | Full QA regression suite; docs/qa.md, urls.md, ux.md, automation.md (presence not verified) |
| **Phase 9** | Full BI ad-hoc report builder; GraphQL; ML model registry/inference; OR-tools timetabling; full video session + attendance sync; dispute handling/payout jobs |
| **Nice-to-have** | Transport, Hostel, Canteen, Health, Inventory, Biometric (missing) |
| **RUNMYCAMPUS_ROADMAP_TASKS** | Self-service tenant signup; UK term preset; nested tenancy; certification/badge expiry; Redis tenant cache; full Predictive Engine (pgvector, nightly risk); full At-Risk/Intervention as specified; full Executive Dashboard; 100+ languages; schema-per-tenant evaluation |
| **Codebase audit** | DashboardTemplate / Configuration Hub; OnboardingService as described; verify_region_coverage; some docs |

---

## 14. How to use this audit

1. **Canonical status:** For architecture roadmap items (14.x, 15.x, 16.x, 17.x, 18.x, 26.x, 29.x, etc.), **ROADMAP_DUE_TODAY.md** is the single source of truth; all those items are implemented (or stubbed).
2. **Task lists:** RUNMYCAMPUS_ROADMAP_TASKS and phase7/PHASE_9/PHASE7_NICE_TO_HAVE contain a mix of implemented and not; this audit table gives the snapshot above.
3. **Updating:** When implementing a "Not" or "Partial" item, update this doc and the source roadmap doc so the next audit stays accurate.
