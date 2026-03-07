# Section 11 — Category Killers (Implementation Summary)

**Reference:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md checklist 11.3, 11.4, 11.5.

---

## 11.3 Benchmark intelligence

**Scope:** Peer benchmarking, operational maturity scoring, forecast scenarios, risk alerts, intervention suggestions.

**Implemented:**

- **App:** `apps.customersuccess`
- **Models:** `BenchmarkCohort`, `TenantMaturityScore`, `ForecastScenario`, `TenantRiskAlert`, `TenantInterventionSuggestion`
- **Services:** `get_peer_school_ids()`, `get_peer_benchmark_metrics()` (peer avg maturity/health)
- **Super APIs (all under `/super/`, require Super Admin):**
  - `GET /super/customer-success/api/benchmark/cohorts/` — list benchmark cohorts
  - `GET /super/customer-success/api/benchmark/peer-metrics/?school_id=<uuid>` — peer avg maturity & health
  - `GET /super/customer-success/api/maturity-scores/?school_id=<uuid>` — maturity scores for a school or all
  - `GET /super/customer-success/api/risk-alerts/?school_id=&acknowledged=0|1` — tenant risk alerts
  - `GET /super/customer-success/api/intervention-suggestions/?school_id=&dismissed=0|1` — intervention suggestions
- **Super dashboard:** `/super/customer-success/` — HTML view with risk alerts, suggestions, workflow failures, health scores

**Optional next steps:** Background job to compute maturity scores per dimension; forecast scenario CRUD; intervention suggestions generated from risk alerts or maturity gaps.

---

## 11.4 Customer success layer

**Scope:** Tenant health scores, workflow failure detection, admin inactivity alerts, support co-pilot, guided onboarding, shadow sessions with masking, auto-ticket creation.

**Implemented:**

- **Models:** `TenantHealthScore`, `WorkflowFailureEvent`, `AdminInactivityAlert`, `AutoTicketRule`
- **Health score:** `compute_tenant_health_score(school)` from last_activity, workflow failures (last 14d), and adoption placeholder; `ensure_health_score_record(school)` persists one per day.
- **Workflow failure detection:** When `run_workflow()` has any action with `error`, `record_workflow_failure()` is called (in `apps.siteconfig.workflow_engine`), creating `WorkflowFailureEvent` and optionally creating a `GlobalSupportTicket` if an `AutoTicketRule` with trigger `workflow_failure` exists.
- **Super APIs:**
  - `GET /super/customer-success/api/tenant-health/?school_id=` — tenant health (computed/stored)
  - `GET /super/customer-success/api/workflow-failures/?school_id=&limit=50`
  - `GET /super/customer-success/api/admin-inactivity-alerts/?school_id=`
- **Auto-ticket:** `create_auto_ticket(school, rule, trigger_context)` creates a `GlobalSupportTicket` with metadata `source=auto_ticket_rule`; rules are configured via `AutoTicketRule` (trigger: workflow_failure, health_below, inactivity_days, risk_alert_red).

**Deferred / placeholder:** Support co-pilot (UI/API), guided onboarding (existing portal onboarding extended as needed), shadow sessions with masking (policy/doc), admin inactivity detection (scheduled task to create `AdminInactivityAlert` and optionally notify/create ticket).

---

## 11.5 Public website superiority

**Scope:** Category clarity, segmented journeys, interactive previews, clean demo, proof, vertical landings, migration-first messaging, “why switch”, localized by region/school type/ROI, security/compliance trust center, app marketplace showcase.

**Implemented:**

- **Marketing page definitions** (in `apps.schools.marketing_views.MARKETING_PAGE_DEFINITIONS`) and **public routes:**
  - `/why-switch/` — migration-first, why switch
  - `/verticals/` — by school type (K12, international, districts), ROI-oriented
  - `/trust-center/` — security/compliance trust center
  - `/app-marketplace/` — app marketplace showcase (blueprints, integrations, governed rollout)
- **Existing:** Category clarity and segmented journeys via product, solutions, pricing, compare, case-studies; `security-compliance` and `integrations`; regional landings (`/cm/`, `/ca/`, `/<language_code>/<country_code>/`); `topical_marketing_landing` for solutions by topic.

**Optional next steps:** Interactive previews, clean demo tenant flow, localized ROI pages per region/school type, A/B copy for “why switch” by segment.

---

## Files touched

- `apps/customersuccess/` — new app (models, services, views_super, migrations)
- `apps/schools/super_urls.py` — customer-success routes
- `apps/siteconfig/workflow_engine.py` — record workflow failure on action error
- `config/settings.py` — INSTALLED_APPS + customersuccess
- `config/public_urls.py` — why-switch, verticals, trust-center, app-marketplace
- `apps/schools/marketing_views.py` — MARKETING_PAGE_DEFINITIONS for 11.5
- `templates/customersuccess/super_dashboard.html` — super dashboard HTML
