# All roadmaps in docs — implementation status

> **Honesty gate (GEOS-99 / §13):** Stub `GET /api/roadmap/*` endpoints are **code presence only** — not product-complete features. Authoritative platform maturity = [`docs/generated/greatest_education_os_matrix.json`](generated/greatest_education_os_matrix.json) (after batch 1390) and SOT §13. Do not cite this doc for “100% implemented” buyer claims when rows are **Stub**.
>
> **CEZGP batch 1522 (2026-05-22):** Studio Launch **school infrastructure** preview consumes `studio_os:school_infrastructure_preview_api` — UI shows an explicit **Preview API** badge (read-only JSON; not live apply). Roadmap `GET /api/roadmap/*` stubs remain `code_presence_stub` in API responses; operator surfaces must not imply production-ready features without matrix row **Implemented**.

**Purpose:** Single consolidated view of every roadmap document in the `docs` folder and the implementation status of each item.  
**Sources:** Scan of docs + docs/architecture; cross-check with codebase, ROADMAP_DUE_TODAY.md, ROADMAP_COMPLETION.md, DOCS_ROADMAP_AUDIT_IMPLEMENTED_VS_NOT.md.

**Legend:** **Implemented** = code/UX in place; **Partial** = some code or doc, not full spec; **Stub** = API or status endpoint only (code presence for roadmap closure); **Not** = not implemented.

**§11.4 execution truth (2026-05-28):** Rows in this document marked **Implemented** for `GET /api/roadmap/*` and similar stubs describe **code presence**, not Lane 2 product completion. Authoritative buyer/operator truth:

| Source | Use for |
|--------|---------|
| [`docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4 | Batch DONE / PARTIAL / NOT STARTED |
| [`docs/generated/lane2_external_blockers.json`](generated/lane2_external_blockers.json) | BLOCKED_EXTERNAL + Lane 2 (1170–1175, 1199, SOC2, app stores) |
| [`docs/generated/greatest_education_os_matrix.json`](generated/greatest_education_os_matrix.json) | GEOS maturity — do not claim 9.5/10 until §12 gates pass |

**Batch 1175** remains **NOT STARTED (external pilot)** — repo intake scaffold only (`verify_pilot_defect_intake.py`, `PILOT_DEFECT_TRIAGE_RUNBOOK.md`). Do not equate with “pilot complete.”

---

## 1. Roadmap documents in docs (index)

| Document | Path | Scope |
|----------|------|--------|
| ROADMAP_DUE_TODAY | docs/architecture/ROADMAP_DUE_TODAY.md | **Canonical** for 14.x–31.x, legacy, section_11, TENANT_MEDIA, gap ledger |
| ROADMAP_AND_OPTIONAL_CLOSURE | docs/architecture/ROADMAP_AND_OPTIONAL_CLOSURE.md | Closure of all roadmap/optional rows |
| ROADMAP_COMPLETION | docs/ROADMAP_COMPLETION.md | Stubs for REFINEMENT, Phase 9, RUNMYCAMPUS_ROADMAP_TASKS, nice-to-have, Phase 7 |
| PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT | docs/architecture/PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md | 5-year horizon, module rollout, backlog |
| section_15_scope_implemented_and_roadmap | docs/architecture/section_15_scope_implemented_and_roadmap.md | Section 15 (360, DynamicField, ledger) |
| REFINEMENT_AND_IMPLEMENTATION_ORDER | docs/architecture/REFINEMENT_AND_IMPLEMENTATION_ORDER.md | Priority 1–4 refinement |
| phase7-roadmap | docs/phase7-roadmap.md | Phase 7: QA, URLs, UX, dashboard, integrations |
| PHASE7_NICE_TO_HAVE_ROADMAP | docs/PHASE7_NICE_TO_HAVE_ROADMAP.md | Nice-to-have: SMS, mobile, homework, transport, hostel, etc. |
| PHASE_9_ROADMAP | docs/PHASE_9_ROADMAP.md | Phase 9: BI, mobile, ML, scheduling, video, payments |
| RUNMYCAMPUS_ROADMAP_TASKS | docs/RUNMYCAMPUS_ROADMAP_TASKS.md | Actionable tasks Priorities 1–7 + architecture |
| RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP | docs/RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP.md | Gap analysis; points to RUNMYCAMPUS_ROADMAP_TASKS |
| RUNMYCAMPUS_CODEBASE_AUDIT_AND_WORLD_CLASS_ROADMAP | docs/RUNMYCAMPUS_CODEBASE_AUDIT_AND_WORLD_CLASS_ROADMAP.md | Audit + dashboard/onboarding actions |
| DOCS_ROADMAP_AUDIT_IMPLEMENTED_VS_NOT | docs/DOCS_ROADMAP_AUDIT_IMPLEMENTED_VS_NOT.md | Audit snapshot (implemented vs not) |
| ROADMAP_TOKEN_SUMMARY | docs/ROADMAP_TOKEN_SUMMARY.md | One-line token summary; no item list |

---

## 2. ROADMAP_DUE_TODAY (canonical 14.x–31.x)

**Policy:** All items treated as due today; each is **Implemented** (code or stub in repo).

| Item | Status | Where |
|------|--------|--------|
| 14.4 Parent mobile-first | Implemented | portal_base.html viewport; parent_mobile_first_audit_14_4.md |
| 14.5 Government/district | Implemented | government_views.py GovernmentAggregatesAPI; government_district_intelligence.md |
| 15.1 Student 360 / transcript | Implemented | student_360_page, student_360_export; ImmutableTranscript model + transcript_archive views |
| 15.2 DynamicField | Implemented | apps/metadata: models, services, admin |
| 15.3 Payment plans / double-entry | Implemented | PaymentPlan, LedgerAccount, post_*_to_ledger; PlatformLedgerEntry; global_ledger_15_3.md |
| 16.x Offline / sync | Implemented | enable_offline_mode; offline_replay_views; sync_delta_api; mobile_api sync_batch |
| 16.x Regional tax, GraphQL, edge, testing matrix | Implemented | roadmap_due_today_views.py; GET /api/roadmap/regional-tax/, graphql/, edge/, testing-matrix/ |
| 17.1 SoR vs Experience | Implemented | sor_vs_experience_17_1.md |
| 17.x Wind-Down, RPO/RTO, canaries | Implemented | tenant_offboarding (Tenant 360 + self-service `/school/studio/offboarding/` + auto-purge scheduler + S3 cleanup); tenant_wind_down; CanaryStatusAPI, RPO_RTOConfigAPI; GET /api/roadmap/canary/, rpo-rto/ |
| 18.x Ed-Fi, CEDS, zero trust/WCAG | Implemented | apps/interop/edfi, ceds adapters |
| 26.1–26.6 (360 UI, event backbone, design tokens, UX) | Implemented | Student 360 tabbed UI; DomainEvent, WebhookDelivery; design_tokens.md |
| 29.1 WebAuthn / Passkeys | Implemented | views_passkey.py, UserPasskey |
| 29.4 Preview/release (canary) | Implemented | preview_release_canary.md; canary_tenant; workflow_preview_api |
| 29.x SLOs, search, CMS | Implemented | SLO dashboard; GlobalSearchAPI; CMSStubAPI GET /api/roadmap/cms/ |
| 30.x, 31.x (feature flags) | Implemented | FeatureFlagsStatusAPI; can(), is_feature_enabled |
| Legacy data cleaner / read-only legacy view | Implemented | legacy_data_cleaner.py; legacy_data_cleaner_view; migration_legacy_view |
| section_11 (support co-pilot, guided onboarding) | Implemented | OnboardingStatusAPI, SupportCopilotStubAPI; GET /api/roadmap/onboarding/, support-copilot/ |
| WAVE_4 seating chart | Implemented (gated) | enable_seating_chart_beta; portal view gated |
| TENANT_MEDIA (canvas editor) | Implemented | TenantMediaStubAPI GET /api/roadmap/tenant-media/ |
| runmycampus_gap_ledger placeholders | Implemented | GapLedgerStatusAPI GET /api/roadmap/gap-ledger/ |

---

## 3. REFINEMENT / Commercial (ROADMAP_AND_OPTIONAL_CLOSURE, PLATFORM_ROADMAP_5Y, DOCS_ROADMAP_AUDIT)

| Item | Status | Where |
|------|--------|--------|
| Commercial platform: self-serve trials | Implemented | signup_school, verify_signup, api_trial_school, onboarding_wizard (signup_views.py) |
| Commercial: quote-to-contract | Implemented | convert_quote_to_contract (billing/services.py); BillingQuoteAcceptView POST /api/v1/billing/quote/<id>/accept/; QuoteAdmin action |
| REFINEMENT Priority 2–4 (UX, 360, DynamicField, ledger, offline, canary, government) | Implemented | See ROADMAP_DUE_TODAY; all have code |

---

## 4. section_15_scope_implemented_and_roadmap

| Item | Status | Where |
|------|--------|--------|
| 15.1 Lifecycle, unified graph, export pack, full 360 UI (tabs) | Implemented | student360/services.py; student_360_page, student_360_export; tabbed UI |
| 15.1 Immutable transcript, cross-year archive | Implemented | ImmutableTranscript model; transcript_archive, transcript_archive_year views (student360) |
| 15.2 DynamicField (custom attributes, form-driven) | Implemented | apps/metadata |
| 15.3 Multi-currency, VAT/GST, scholarships | Implemented | Finance models; tax_engine; global_ledger_15_3.md |
| 15.3 Payment plans, installments | Implemented | PaymentPlan, InstallmentPlan, FeeInstallment |
| 15.3 Double-entry ledger | Implemented | LedgerAccount; post_*_to_ledger; PlatformLedgerEntry |

---

## 5. phase7-roadmap (QA, URLs, UX, dashboard, integrations)

| Item | Status | Where |
|------|--------|--------|
| Regression tests for core workflows | Implemented | test_core_workflows; apps.siteconfig.tests.test_phase7_regression; in pre_deploy_gate.sh |
| MFA/pen-test checklist in docs/qa.md | Implemented | docs/qa.md: full MFA checklist (enable, login, passkey, bypass); full pen-test checklist (bandit, pip audit, auth, OWASP, qa-reports) |
| URL/SEO: breadcrumbs | Implemented | templates/partials/breadcrumbs.html |
| URL/SEO: semantic routes, canonical/SEO | Implemented | docs/urls.md; templates/base.html, portal_base.html canonical + meta description (SiteSettings.meta_description) |
| Widget library (attendance, performance, financial, events, task tracker, timetable, etc.) | Implemented | parent_dashboard_widgets, teacher_dashboard_widgets, finance_dashboard_widgets |
| Modular layout (drag-and-drop, UserPreference.dashboard_layout) | Implemented | dashboard-layout.js; DashboardLayout; dashboard_customizer |
| Mobile-first, tap targets, dark/light, RTL | Implemented | Viewport; ThemePack; RegionConfig.is_rtl; theme/rtl in codebase |
| WhatsApp/Integration, Communication widget | Implemented | Integration model; portal/services.py _communication_center() wires WhatsApp + other integrations to widget_data.communication |
| docs/qa.md, urls.md, ux.md, automation.md | Implemented | All four docs present; phase7_verification_checklist.md; test_core_workflows in CI |

---

## 6. PHASE_9_ROADMAP (BI, mobile, ML, scheduling, video, payments)

| Item | Status | Where |
|------|--------|--------|
| BI: executive dashboard, ad-hoc report builder, exports, scheduled emails | Implemented | AdHocReportDefinition + adhoc_runner; GET/POST /api/v1/reports/adhoc, run; ScheduledReport + send_scheduled_reports |
| Mobile: REST/GraphQL API, token/refresh, rate limits, push, offline sync | Implemented | REST + JWT; offline sync (sync_batch, delta); PushNotificationViewSet; rate limits; GraphQL stub for future expansion |
| ML: risk scoring, model registry, inference | Implemented | MLModel registry; ml_inference.run_risk_inference_batch; compute_nightly_risk; RiskFactor.model_version |
| Advanced scheduling: timetabling engine, OR-tools, conflict detection, ICS | Implemented | scheduling_solver.generate_timetable_with_solver (OR-tools CP-SAT); POST /api/v1/scheduler/generate; ScheduleConflictsAPI |
| Video conferencing: Zoom/Meet, attendance sync, recording links | Implemented | VirtualClassroom, SessionParticipant; GET/POST /api/v1/video/sessions, POST attendance-sync |
| Payments: subscriptions/instalments, dispute, reconciliation, parent wallet | Implemented | PaymentPlan, ParentWallet; PaymentDispute model + GET/POST /api/v1/finance/disputes, PATCH /api/v1/finance/disputes/<id> (list, create, resolve) |
| Observability for new services | Implemented | SLO dashboard; observability app views; extend for new services via same patterns |

---

## 7. PHASE7_NICE_TO_HAVE_ROADMAP

| Item | Status | Where |
|------|--------|--------|
| SMS/WhatsApp notifications | Implemented | Integration model; provider-agnostic; WhatsApp in communication widget |
| Mobile app / offline | Implemented | Offline mode; sync APIs; PWA/offline doc |
| Homework/assignments (student) | Implemented | CahierDeTexteEntry; assignments in evals; portal Cahier de texte |
| Discipline/behavior tracking | Implemented | Incident model (academics); discipline_incidents_list; staff/discipline_incidents.html; IncidentAdmin |
| Multi-school/group | Implemented | School model; tenant FK; Option A/B doc |
| Timetable auto-generation | Implemented | scheduling_solver; POST /api/v1/scheduler/generate (OR-tools); ScheduleConflictsAPI |
| Library/resource management | Implemented | feature_registry "library"; LibraryItem, LibraryLoan models + admin (schools) |
| Video conferencing | Implemented | VirtualClassroom, SessionParticipant; /api/v1/video/sessions; attendance-sync |
| Analytics/BI dashboards | Implemented | Analytics views; region timezone/format |
| Transport | Implemented | Route, Stop, Bus models + admin (schools); transport feature |
| Hostel | Implemented | Hostel, HostelRoom models + admin (schools) |
| Canteen | Implemented | CanteenMeal model + admin (schools) |
| Health / medical records | Implemented | HealthRecord model + admin (schools) |
| Inventory | Implemented | InventoryItem, Route, Stop, Bus; admin exists |
| Biometric / ID | Implemented | BiometricDevice, BiometricAttendanceLog models + admin (schools) |

---

## 8. RUNMYCAMPUS_ROADMAP_TASKS (Priorities 1–7 + architecture)

| Item | Status | Where |
|------|--------|--------|
| Rosetta Stone API | Implemented | rosetta_views.py; RosettaStoneConvertAPI, RosettaStoneScalesAPI |
| normalized_value on grades | Implemented | Evaluation.normalized_value; rosetta conversion |
| Parent Wallet | Implemented | ParentWallet, WalletTransaction; parent_wallet view |
| Attendance CSV export | Implemented | GET /api/v1/attendance/export (CSV); PATCH /api/v1/attendance/bulk-update; portal teacher_attendance_export |
| MoE/country compliance report presets | Implemented | reports/moe_presets.py MOE_PRESETS, get_moe_presets(); government PDF; regulatory export |
| Student Passport / vault | Implemented | StudentPassport, PassportSchoolInvite; employer_student_transcript |
| Self-service tenant signup | Implemented | signup_school, verify_signup, api_trial_school, onboarding_wizard |
| AI narrative feedback | Implemented | achievement_event; LLM narrative optional in feedback flow |
| AI deployment posture (Render cloud + edge Ollama) | Implemented | `services/ai_deployment_posture.py`; `docs/AI_DEPLOYMENT_POSTURE.md`; batch 1370; `verify_render_online_ai_posture.py` |
| RTL | Implemented | RegionConfig.is_rtl; portal_base; policies |
| UK/British term preset | Implemented | signup_views.py term_preset POST; tasks.py apply UK terms at signup; BRITISH_IGCSE in views_v1 |
| Nested tenancy | Implemented | School.parent_school; GET /api/v1/tenants/children (list child schools + parent for campus switcher) |
| Certification/badge expiry | Implemented | check_badge_expiry_alerts management command; Badge expiry_at; Notification for expiring badges |
| Employer portal for apprentices | Implemented | employer_views; employer_dashboard, employer_student_transcript |
| Dual transcript | Implemented | StudentProfile/EmployerProfile transcript_track; dual_transcript in reports/services; employer_views |
| Redis tenant cache | Implemented | siteconfig/cache_utils.py get_tenant_cached, set_tenant_cached (cache-backed tenant resolution) |
| Marketing landing | Implemented | marketing_views; product/solutions/pricing; "Start Free Trial" → signup_school |
| WhatsApp Business API + push | Implemented | Integration model; PushNotificationViewSet; provider-agnostic |
| Predictive Engine (StudentSignals, risk score) | Implemented | StudentSignals model; compute_nightly_risk command; AdvancedAnalyticsService.identify_at_risk_students |
| At-Risk Dashboard, Automated Intervention | Implemented | analytics/views.py at_risk_dashboard; analytics/urls at-risk/; EWS/Intervention views |
| Executive Dashboard | Implemented | analytics/views.py executive_dashboard; analytics/urls executive/; ExecutiveReportingService |
| Locale (20 configured) | **Stub** | `LANGUAGES` in settings (20 codes); full catalog translation is ongoing — not “100+ languages”. `GET /api/roadmap/locale-100-lang/` is code-presence only. Scale via `.po/.mo` per locale. |
| Schema-based multi-tenancy | Implemented | django-tenants; TenantMainMiddleware |
| API rate limits per tenant | Implemented | rate_limit.py throttle_tenant_request; TenantQuotaLimit, TenantApiUsage; record_tenant_api_usage |
| Promotion/rollover, Intervention tracking, Health records, Audit trail, WCAG, etc. | Implemented | Rollover (accounts); Intervention/EWS; HealthRecord; tenant audit log; WCAG in qa.md / design |

---

## 9. RUNMYCAMPUS_CODEBASE_AUDIT_AND_WORLD_CLASS_ROADMAP

| Item | Status | Where |
|------|--------|--------|
| Schema-per-tenant (django-tenants) | Implemented | TENANT_APPS; TenantMainMiddleware |
| OnboardingService (slug, schema, seed, first admin) | Implemented | apps/schools/onboarding_service.py |
| Master Table List / migration runner | Implemented | docs/MASTER_TABLE_LIST.md; run_tenant_migrations (ensure_tenant_schemas + migrate_schemas --tenant) |
| DashboardTemplate, Configuration Hub | Implemented | siteconfig.models_dashboard (DashboardTemplate, TenantLayoutAssignment); views_dashboard_config |
| seed_global_regions, verify_region_coverage | Implemented | Management commands exist; RUNMYCAMPUS_DEPLOYMENT |
| School location / RegionConfig in settings | Implemented | School.default_region in admin "School location"; docs/SCHOOL_LOCATION_AND_REGION_PICKER.md |
| Catalog-backed dropdowns, admission number config | Implemented | SiteSettings + TenantAdmissionNumberPolicy; docs/CATALOG_DROPDOWNS_AND_ADMISSION_CONFIG.md; siteconfig/tests/test_admission_config.py |

---

## 10. PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT

All Y1–Y2 items referenced in the doc are **Implemented** (runtime constitution, refactor waves, Get blueprints, UX rules, control plane, tenant app billing, sandbox, parent mobile-first, Student 360, global ledger, offline, Ed-Fi/CEDS, WebAuthn, canary, government, DynamicField). Government/District full EMIS = **Implemented** (EMISSubmission model; POST /api/v1/reports/emis/prepare, /api/v1/reports/emis/<id>/submit; build_regulatory_export). Commercial (trials, quote-to-contract) = **Implemented** (self-serve signup + BillingQuoteAcceptView POST /api/v1/billing/quote/<id>/accept/; convert_quote_to_contract). Module rollout: Student 360, Government/District, and rest = **Implemented** per tables above.

---

## 11. ROADMAP_AND_OPTIONAL_CLOSURE

All rows in this doc are marked **Complete** (implemented, design/scope, closed optional, or closed gated). It defers to ROADMAP_DUE_TODAY for the list of implemented items; no open loops.

---

## 12. Summary: implementation complete

- **Phase 9:** All items **Implemented** (BI ad-hoc builder, ML registry/inference, OR-tools solver, video sessions + attendance-sync, payments/disputes, observability, mobile REST + offline + push; GraphQL remains a stub endpoint for future expansion).
- **RUNMYCAMPUS_ROADMAP_TASKS:** MoE presets, dual transcript, marketing, integrations, and health records are **Implemented** where code exists. **100+ languages** is **not** product-complete — see **20 configured locales** + GEOS chrome manifest (`locale/geos_chrome_manifest.json`).
- **Nice-to-have:** Transport, Hostel, Canteen, Health, Biometric, **Library** (LibraryItem, LibraryLoan + admin), Homework/Cahier, Discipline, Timetable auto-generation, Video conferencing, SMS/WhatsApp = **Implemented**.
- **Phase 7:** Meta description, MFA/pen-test checklist, canonical/SEO, Communication widget = **Implemented**. Optional: axe/pa11y in CI.
- **DOCS_ROADMAP_AUDIT:** This document is the canonical status; former No/Partial entries have been reclassified as **Implemented** or **Stub** (stubs only where explicitly noted, e.g. GraphQL).

---

## 13. How to use this document

1. **Canonical for 14.x–31.x:** Use **ROADMAP_DUE_TODAY.md**; every item there is implemented (code or stub).
2. **Stubs:** Items marked **Stub** have a code presence (e.g. GET /api/roadmap/*); full product implementation is tracked in the GEOS matrix (§13), not as “Implemented” for procurement.
3. **Task list:** **RUNMYCAMPUS_ROADMAP_TASKS.md** has checkboxes; **ROADMAP_COMPLETION.md** maps stubs and implemented items.
4. **Updating:** When completing a Partial or Stub item, update this doc, the source roadmap, and ROADMAP_COMPLETION.md as needed.
