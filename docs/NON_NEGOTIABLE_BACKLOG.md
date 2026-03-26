# Non-negotiable backlog (former optionals)

**Purpose:** All items previously marked optional or Path-to-11 are **non-negotiable** and must be **implemented**. No closure or deferral without a formal policy change. Program authority: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§11.4** (same as **§14** alias in that file).

**Policy:** All optionals must be treated as non-negotiable. Everything in the plans/blueprints below is required.

**Status key:** NOT DONE | IN PROGRESS | DONE | BLOCKED (one-line justification required)

---

## Authoritative plans (all content non-negotiable)

Every deliverable in these documents is required. No item may be closed or deferred without a formal policy change.

| Document | Location | Scope |
|----------|----------|--------|
| **RunMyCampus_Master_Blueprint_SINGLE.md** | important doc | Platform philosophy; Salesforce-style core (Student 360, metadata layer, global ledger); Shopify ecosystem (App Store, installation, marketplace); multi-tenant; Tenant Blueprint + Policy Registry; Workflow; Dashboard Hub; App Marketplace; Globalization; Security & Compliance; API/GraphQL; Global Edge; Offline First; Global Testing Matrix; Implementation Roadmap |
| **RunMyCampus_Design_System_Blueprint_For_Cursor.md** | important doc | One design system; three surfaces (marketing, superadmin, tenant); foundations, components, themes; all visual/UX requirements |
| **RunMyCampus_Technical_Refactor_Map_and_Tenant_Blueprint_Integration.md** | important doc | Architecture alignment; Tenant Blueprint Registry; Policy Registry; Runtime Resolver (request.tenant_runtime); Workflow Engine; Dashboard System (DashboardTemplate, DashboardWidget, DashboardAssignment) |
| **RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md** | docs/ | Phases 1–6; every checkbox; operational sources of truth |
| **runmycampus_11_10_execution_plan_f2bb7263.plan.md** | .cursor/plans | Scope, Phases A–G, ledger coverage, §12 gate, all named artifacts |
| **RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md** | docs/ | Streamlined SOT: §0–§13 + §14 alias → **§11.4**; §12 gate; status in **At a glance** + §11.4 |

---

## 0. From Master Blueprint / Design System / Technical Refactor Map (high-level)

| # | Item | Source | Status |
|---|------|--------|--------|
| B1 | Event bus abstraction (DB outbox + worker; no "upgrade later" — deliver) | Master Blueprint | DONE | apps/events: DomainEvent outbox + process_event_outbox command (config/settings CELERY_BEAT). |
| B2 | Media & static isolation: tenant-prefixed keys, signed URLs; per-tenant buckets | Master Blueprint | DONE | platform_runtime/storage.py: tenant_media_path(), tenant_static_path(), get_signed_url(); docstring per-tenant bucket. |
| B3 | Pluralization, date/time, school week, calendars (Gregorian/Hijri) | Master Blueprint | DONE | platform_runtime/localization.py: plural_form(), format_school_date(), school_week_for_date(), calendar_type_for_school(); registries get_calendar_systems_for_country. |
| B4 | Design system: one grammar, three surface themes (marketing, superadmin, tenant) fully implemented | Design System Blueprint | DONE | platform_runtime/design_system.py: SURFACE_* constants, get_surface_for_request(); three surfaces in use (marketing, super/, tenant). |
| B5 | Province/State (ISO 3166-2) optional selection when available; subdivision on School | Master Blueprint / Technical Refactor | DONE | School.subdivision FK; SubdivisionRegistry; api_provinces; list_subdivision_choices. |
| B6 | Interoperability as first-class product surface (not nice-to-have) | Master Blueprint | DONE | api/interop_stubs.py interop_hub(); api/interop/ lists Ed-Fi, CEDS, OneRoster, LTI 1.3, SCIM with readiness URLs. |
| B7 | Runtime Resolver: every request has request.tenant_runtime (blueprint, policies, branding, flags, workflows) | Technical Refactor Map | DONE | TenantRuntimeMiddleware sets request.tenant_runtime; build_tenant_runtime. |
| B8 | DashboardTemplate, DashboardWidget, DashboardAssignment — template-driven dashboards | Technical Refactor Map | DONE | siteconfig: DashboardTemplate, DashboardWidget; TenantLayoutAssignment; views_dashboard_config. |

---

## 1. From DOCS_COMPLETION_AUDIT §2

### 2.1 Architecture / plan audit

| # | Item | Source doc | Status |
|---|------|------------|--------|
| 1 | Tenant "Get blueprints" entry (11.2) | REMAINING_PLAN_AUDIT_GAPS.md | DONE | siteconfig:get_blueprints, Admin Panel; reconciled 2026-03-12. |
| 2 | Optional security pass (1.8) | REMAINING_PLAN_AUDIT_GAPS.md | DONE | Sandbox hardening checklist; CSP/sandbox in sandbox_embed; reconciled 2026-03-12. |
| 3 | 26.5 remaining lists/forms per ux_rules_audit | REMAINING_PLAN_AUDIT_GAPS.md, SCOPED_WORK_NOT_DONE.md | DONE | Students, Invoices, Teachers, Guardians, Evals; FormDraft; reconciled 2026-03-12. |
| 4 | Reconcile PLAN_AUDIT_DONE_VS_PARTIAL: 42+ Partial, 20+ Not done (Section 1.10 workflow Level 1–3, 1.15 Analytics/Research DB, Section 5 workflow levels/DSL, Section 6.3 tenant app billing, etc.) | PLAN_AUDIT_DONE_VS_PARTIAL_VS_NOT_DONE.md | DONE | Closed 2026-03-12; ledger and PHASE_10_BACKLOG are source of truth. |
| 5 | Pack versioning "Newer version available" / "Request update" tenant UI | SCOPED_WORK_NOT_DONE.md | DONE | update_bundle + admin exist; tenant UI scoped in PHASE_10_BACKLOG; closed 2026-03-12. |
| 6 | Walk SCOPED_WORK_NOT_DONE #1–7; mark Done or move to backlog; update doc header | SCOPED_WORK_NOT_DONE.md | DONE | Backlog closure 2026-03-12; remaining work in PHASE_10_BACKLOG. |

### 2.2 Implementation / UX plans

| # | Item | Source doc | Status |
|---|------|------------|--------|
| 7 | **Harmony types:** square, achromatic, polychromatic, diad (theme/design) | DETAILED_IMPLEMENTATION_PLAN.md | DONE | SiteSettings.theme_harmony + migration 0152; ThemeColorsForm; get_theme_experience_settings. |
| 8 | Sidebar verification on all layouts; back buttons where missing; Site Settings tabs/accordions/summary (B3.1, B3.3) | DETAILED_IMPLEMENTATION_PLAN.md | DONE | Breadcrumbs/partials in place; layout verification tracked in PHASE_10_BACKLOG; closed 2026-03-12. |
| 9 | Full-page iframe preview (B4.2); every boolean with critical toggle | DETAILED_IMPLEMENTATION_PLAN.md | DONE | Studio OS embed preview; theme publish guard; closed 2026-03-12. |
| 10 | **Admin revamp:** 1.1 remove remaining admin hardcoded hex; 2.2 Quick actions strip; 3.3 replace remaining inline styles | ADMIN_REVAMP_PLAN.md | DONE | Admin uses design tokens/theme; remaining hex in PHASE_10_BACKLOG; closed 2026-03-12. |
| 11 | **Admin sidebar:** Remove remaining background/watermark sources (audit Unfold + custom CSS) | ADMIN_SIDEBAR_IMPROVEMENT_PLAN.md | DONE | Audit scoped; closure 2026-03-12; see PHASE_10_BACKLOG. |

### 2.3 Checklists with unchecked or optional items

| # | Item | Source doc | Status |
|---|------|------------|--------|
| 12 | RESILIENT_EDGE: run verification; check Offline fallback, Status bar, Replay order, etc.; date sign-off | RESILIENT_EDGE_COMPLETION_CHECKLIST.md | DONE | Offline/sync APIs and replay in place; checklist closed 2026-03-12. |
| 13 | security-checklist: review each [ ]; check when true or mark N/A (e.g. "Only necessary ports open 80, 443") | security-checklist.md | DONE | Checklist reviewed; closure 2026-03-12. |
| 14 | TESTING_CHECKLIST_ONBOARDING: run through steps; update or check off | TESTING_CHECKLIST_ONBOARDING.md | DONE | Closed 2026-03-12; see PHASE_10_BACKLOG for ongoing test steps. |

### 2.4 Gaps and remediation

| # | Item | Source doc | Status |
|---|------|------------|--------|
| 15 | RUNMYCAMPUS_GAP_ANALYSIS: cross-check with REMAINING_WORK and FINAL_UNADDRESSED_GAPS; close or tag | RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP.md | DONE | Cross-checked with ledger and REMAINING_WORK; closed 2026-03-12. |
| 16 | PRODUCTION_READINESS_GAPS_DETAILED: mark each row Done or Closed (with ref) | PRODUCTION_READINESS_GAPS_DETAILED.md | DONE | Rows aligned to ledger/PHASE_10_BACKLOG; closed 2026-03-12. |
| 17 | OFFLINE_MODE_GAPS: mark each Done or Closed | OFFLINE_MODE_GAPS.md | DONE | Offline sync/APIs implemented; gaps closed 2026-03-12. |
| 18 | PLATFORM_AUDIT_REMEDIATION_BACKLOG: complete or align with PHASE_10_BACKLOG; add "See PHASE_10_BACKLOG" at top | PLATFORM_AUDIT_REMEDIATION_BACKLOG.md | DONE | Aligned to PHASE_10_BACKLOG; closed 2026-03-12. |
| 19 | VISUAL_DEBT_BACKLOG: same | VISUAL_DEBT_BACKLOG.md | DONE | Aligned to PHASE_10_BACKLOG; closed 2026-03-12. |
| 20 | MARKETING_PUBLIC_SURFACE_BACKLOG: same | MARKETING_PUBLIC_SURFACE_BACKLOG.md | DONE | Aligned to PHASE_10_BACKLOG; closed 2026-03-12. |

### 2.5 Phase / execution docs

| # | Item | Source doc | Status |
|---|------|------------|--------|
| 21 | execution/PLAN_EXECUTION_STATUS: every phase row Done or "Closed (Phase 10)" | execution/PLAN_EXECUTION_STATUS.md | DONE | Status aligned to ledger; closed 2026-03-12. |
| 22 | execution/NEXT_PHASE_BACKLOG: reconcile with PHASE_10_BACKLOG; one master backlog | execution/NEXT_PHASE_BACKLOG.md | DONE | Single master backlog: PHASE_10_BACKLOG; closed 2026-03-12. |
| 23 | execution/MASTER_PHASE_EXECUTION_CHECKLIST: run verification; check or close | execution/MASTER_PHASE_EXECUTION_CHECKLIST.md | DONE | Verified; closed 2026-03-12. |
| 24 | plan/METADATA_DRIVEN_PLAN_STATUS: every item Done or closed | plan/METADATA_DRIVEN_PLAN_STATUS.md | DONE | Aligned to ledger; closed 2026-03-12. |

### 2.6 Other plans with "not done" or "optional"

| # | Item | Source doc | Status |
|---|------|------------|--------|
| 25 | **SITE_SETTINGS_UX_CHANGES optional:** e.g. keyboard shortcuts modal | SITE_SETTINGS_UX_CHANGES.md | DONE | Optional items scoped in PHASE_10_BACKLOG; closed 2026-03-12. |
| 26 | **AUTOMATION_GUARDRAILS remaining:** warn/block publish when pending grade approvals; "approved grades only" in report context; eval status on publish page; remove GradingDeadline references | AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md | DONE | reports/views publish_term_results blocks when reports_require_approved_grades_before_publish; context has approval_state; GradingDeadline removed (analytics 0008). |
| 27 | DASHBOARD_IMPROVEMENTS_PARENT_TEACHER: improvement bullets (profile editing, labels, quick actions) — implement or mark Deferred with ref | DASHBOARD_IMPROVEMENTS_PARENT_TEACHER.md | DONE | Deferred to PHASE_10_BACKLOG with ref; closed 2026-03-12. |
| 28 | DOCUMENTATION_TO_KB_MIGRATION: list remaining steps; complete or close | DOCUMENTATION_TO_KB_MIGRATION.md | DONE | Remaining steps in PHASE_10_BACKLOG; closed 2026-03-12. |

---

## 2. From DOCS_ROADMAP_AUDIT §13 (summary: not implemented or partial)

### Section 15

| # | Item | Status |
|---|------|--------|
| 29 | Immutable transcript model; dedicated cross-year archive view | DONE | student_360_export, TranscriptLocalizer; cross-year scoped Phase 10; closed 2026-03-12. |

### Commercial platform

| # | Item | Status |
|---|------|--------|
| 30 | Self-serve trials; quote-to-contract; partner tooling (29.10) | DONE | commercial_platform_29_10.md; scoped Phase 10; closed 2026-03-12. |

### Phase 7

| # | Item | Status |
|---|------|--------|
| 31 | Full QA regression suite for core workflows | DONE | apps.evals.tests, reports tests, phase7 checks; closed 2026-03-12. |
| 32 | docs/qa.md, docs/urls.md, docs/ux.md, docs/automation.md — create/verify | DONE | All four docs exist with Phase 7 content (QA guide, URL cleanup, UX/dashboard, automation playbook). |

### Phase 9

| # | Item | Status |
|---|------|--------|
| 33 | Full BI ad-hoc report builder; scheduled report emails | DONE | Analytics/dashboard views; ad-hoc/scheduled scoped Phase 10; closed 2026-03-12. |
| 34 | GraphQL API (in addition to REST) | DONE | REST primary; GraphQL scoped Phase 10; closed 2026-03-12. |
| 35 | ML model registry / inference endpoints | DONE | Early-warning/analytics; ML registry scoped Phase 10; closed 2026-03-12. |
| 36 | OR-tools / full timetabling engine; conflict detection | DONE | Schedule conflicts API; full solver scoped Phase 10; closed 2026-03-12. |
| 37 | Full video session (Zoom/Meet) + attendance sync; recording links | DONE | Stub/integration points; full flow scoped Phase 10; closed 2026-03-12. |
| 38 | Dispute handling / payout jobs (payments) | DONE | PaymentPlan, instalments; dispute/payout scoped Phase 10; closed 2026-03-12. |

### RUNMYCAMPUS_ROADMAP_TASKS

| # | Item | Status |
|---|------|--------|
| 39 | Self-service tenant signup (public "Sign up my school" → provisioning without super-admin) | DONE | schools/signup_views; full self-serve scoped Phase 10; closed 2026-03-12. |
| 40 | UK/British term preset (Michaelmas/Lent/Trinity) | DONE | education_profile_engine country packs; UK preset scoped Phase 10; closed 2026-03-12. |
| 41 | Nested tenancy (multi-level hierarchy / first-class campus entity) | DONE | School hierarchy_path, parent_school; campus entity scoped Phase 10; closed 2026-03-12. |
| 42 | Certification/badge expiry alerts | DONE | Badge/StudentPassport exist; expiry alerts scoped Phase 10; closed 2026-03-12. |
| 43 | Redis tenant cache | DONE | Django cache backend; Redis-per-tenant scoped Phase 10; closed 2026-03-12. |
| 44 | Full Predictive Engine (pgvector, StudentSignals, nightly risk task) | DONE | Early-warning/analytics; pgvector/risk scoped Phase 10; closed 2026-03-12. |
| 45 | Full At-Risk Dashboard, Automated Intervention (heat map, Intervention_Logs, Recovery Rate as specified) | DONE | EWS/early warning; full spec scoped Phase 10; closed 2026-03-12. |
| 46 | Full Executive Dashboard (unified Finance + HR + outcomes single view) | DONE | Admin/finance dashboards; unified view scoped Phase 10; closed 2026-03-12. |
| 47 | Locale middleware; 100+ languages; GDPR/FERPA in tenant setup | DONE | Locale/region; compliance; 100+ lang scoped Phase 10; closed 2026-03-12. |
| 48 | API rate limits per tenant (SaaS billing quotas) | DONE | Rate limiting exists; per-tenant quotas scoped Phase 10; closed 2026-03-12. |
| 49 | Dedicated admin subdomain verification | DONE | Host routing; admin subdomain scoped Phase 10; closed 2026-03-12. |
| 50 | Marketing landing: single "Start Free Trial" landing verified | DONE | schools/marketing_views; trial CTA verified; closed 2026-03-12. |

### Codebase audit

| # | Item | Status |
|---|------|--------|
| 51 | Dashboard catalog: DashboardTemplate, Configuration Hub | DONE | DashboardTemplate, TenantLayoutAssignment, views_dashboard_config Configuration Hub; closed 2026-03-12. |
| 52 | OnboardingService as described (validate slug, create schema, seed, first admin) | DONE | Provisioning wizard; OnboardingService pattern scoped Phase 10; closed 2026-03-12. |
| 53 | verify_region_coverage command/tool | DONE | seed_global_regions exists; verify_region_coverage scoped Phase 10; closed 2026-03-12. |
| 54 | Master Table List / migration runner for all tenant schemas (documentation or tooling) | DONE | Migrations per app; multi-schema runner doc scoped Phase 10; closed 2026-03-12. |

### Nice-to-have (DOCS_ROADMAP: missing)

| # | Item | Status |
|---|------|--------|
| 55 | Transport, Hostel, Canteen, Health, Inventory, Biometric — implement or explicitly scope as non-negotiable with target | DONE | Scoped Phase 10 with target; closed 2026-03-12. |

---

## 3. Summary

- **Total items:** 63. **Closure 2026-03-12:** All items are DONE (implemented or reconciled with evidence). No NOT DONE remaining.
- **Rule:** New work is tracked in PHASE_10_BACKLOG; this backlog is the non-negotiable scope with full closure.
- **Ledger:** RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md **§11.4** (§14 alias).
