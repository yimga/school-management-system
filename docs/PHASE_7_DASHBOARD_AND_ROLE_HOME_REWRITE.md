# Phase 7 — Dashboard and role-home rewrite (execution map)

**Canonical plan:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§3.2.1**.

**Status:** **DONE** — implementation merged to repo (2026-03). Historical docs named “Phase 7” (`PHASE_7_COMPLETION.md`, `ux.md`, etc.) refer to **earlier** QA/URL work, not this program.

---

## 1. Goal

- Dashboards answer **one primary question** and expose **one dominant next step** above the fold.
- Role homes are **operating surfaces** (headline → metrics → queue → actions → activity), not undifferentiated card grids.

**Shared implementation**

| Artifact | Role |
|----------|------|
| `templates/components/decision_engine_surface.html` | Five-zone layout + `data-decision-zone` markers |
| `static/css/decision-engine-surface.css` | Shared surface styling + collapsible secondary pattern |
| `phase7_de` (view context) | Headline, metrics, urgent queue, next actions (max 3), activity rows |
| `data-decision-engine="surface"` | Portal / control-plane shells where partial is not inlined |

**Tests / gate:** `apps/dashboard/tests/test_phase7_decision_surface.py`, `apps/dashboard/tests/test_role_home_engine.py` (`SUPERADMIN` → `platform_ops`) — both in `scripts/pre_deploy_gate.sh` `TARGETED_HARDENING_TESTS`. **Template contract:** `scripts/verify_phase7_dashboard_markers.py` (same gate) — every path in §7 must contain `phase7_de`, `decision_engine_surface.html`, or `data-decision-engine=`. **Control-plane closure:** `scripts/verify_control_plane_hub_registry_drift.py` + `apps/dashboard/tests/test_control_plane_hub_registry_drift.py`.

---

## 2. Task 1 — Classification (Strategic / Operational / Analytical)

| Surface | Type | Rationale |
|---------|------|-----------|
| `accounts/backend_dashboard` + `build_dashboard_extras` | **Operational** | Queues, CTAs, role-home engine |
| `finance/dashboard.html` | **Operational** | Receivables, overdue, inbox |
| `analytics/dashboard.html` | **Analytical** (with operational pulse) | Filters, distributions, drill-downs |
| `compliance/dashboard.html` | **Operational** | Integrity, access failures, audits |
| `requests/dashboard.html` | **Operational** | Approval inbox |
| `apicenter/dashboard.html` | **Operational** | Integration kill-switch governance |
| `emis/dashboard.html` | **Operational** | Regulatory export |
| `payroll/dashboard.html` | **Operational** | Runs and payslips |
| `teacher/dashboard.html`, `parent/dashboard.html` | **Operational** | Role-native day-one work |
| `student/learning_home.html` | **Operational** | Learner inbox + syllabus path |
| `schools/super_dashboard.html` | **Strategic** | Fleet / revenue / health |
| `schools/super_support_dashboard.html` | **Operational** | Tickets, SLA |

---

## 3. Task 2 — JTBD (user, job, question, main action)

| Surface | User | JTBD | Main question | Main action |
|---------|------|------|---------------|-------------|
| Backend dashboard | Staff by role | When I land, I want my job’s priority, so I can act fast. | “What must I do first?” | Role-primary CTA (`dashboard_contract.primary_action_count == 1`) |
| Finance | Bursar / finance staff | When I open finance, I want collections health, so I can chase cash. | “What is outstanding and overdue?” | Overdue / generate fees / invoices (trimmed to 3 CTAs) |
| Analytics | Principal / academic admin | When I scan performance, I want risk signals, so I can intervene. | “Where are weak subjects?” | Master sheet / deadlines / executive view |
| Compliance | Admin / security | When I audit, I want integrity and access posture, so I can prove control. | “Is integrity acceptable?” | Playbook / reload / backend home |
| Requests | Approvers | When I triage, I want open volume, so I can clear the queue. | “What is waiting on me?” | Filter pending |
| API Center | Integrations admin | When I govern APIs, I want enablement state, so I can kill-switch safely. | “What is on vs off?” | Return to hub / domain hub |
| EMIS | Registrar / ministry prep | When I export, I want scope counts, so I can file correctly. | “How big is the cohort?” | Jump to export form |
| Payroll | Payroll operator | When I run pay, I want run status, so I can close the period. | “Where is the latest run?” | New run / open latest |
| Teacher hub | Teacher | When I teach, I want class load and alerts, so I can grade and communicate. | “What needs attention today?” | Enter marks |
| Parent hub | Parent / guardian | When I check in, I want family state, so I can support my child. | “How is my child doing?” | Header glance + widgets |
| Student home | Student | When I study, I want tasks and messages, so I don’t miss school. | “Am I set up and informed?” | Messages |
| Super dashboard | Platform ops | When I operate the fleet, I want health, so I can route incidents. | “Is the platform healthy?” | Setup Studio |
| Super support | Support / CS | When I support tenants, I want SLA risk, so I can escalate. | “What is breaching SLA?” | Command center |

---

## 4. Tasks 3–5 (implementation notes)

- **Layout:** All **registered** full-page dashboards (§7) include `phase7_de` + `decision_engine_surface` **or** `data-decision-engine="surface"`; see `verify_phase7_dashboard_markers.py`.
- **Card cemeteries:** Collapsed behind `<details class="de-secondary-collapsible">` on **analytics** (dense KPI grid), **compliance** (full metrics grid), **apicenter** (integration cards).
- **Role homes:** `role_home_engine.ROLE_HOME_BY_ROLE` — `SUPERADMIN` → **`platform_ops`** (distinct from `implementation` for school IT). Admissions/finance/district maps unchanged; student role uses **dedicated** learning home.

---

## 5. Acceptance criteria

| Criterion | Evidence |
|-----------|----------|
| 5-second test | Headline KPI + “Next best actions” in `decision_engine_surface` above fold; teacher/parent retain hero-first layout with explicit `data-decision-zone`. |
| Purpose-built / lower-click | ≤3 next actions on module dashboards; finance hero actions reduced from 4→3; student no longer forced to parent dashboard. |

---

## 6. Related docs

- [runtime_resolvers_and_contracts.md](runtime_resolvers_and_contracts.md) — `DashboardResolver` / runtime contract.
- [DASHBOARD_CLEAN_CLASSY_PLAN.md](DASHBOARD_CLEAN_CLASSY_PLAN.md) — visual discipline.

---

## 7. Full-page dashboard template registry (enforced)

**Source of truth:** `apps/dashboard/phase7_dashboard_templates.py` (`PHASE7_DASHBOARD_TEMPLATES`); enforced by `scripts/verify_phase7_dashboard_markers.py` (pre-deploy gate). **Control-plane closure:** every `control_plane_base.html` extend is either in this registry or in `EXEMPT_CONTROL_PLANE_TEMPLATES` (`apps/dashboard/control_plane_hub_scan.py`), verified by `scripts/verify_control_plane_hub_registry_drift.py`. Paths are under `templates/`.

| Path |
|------|
| `accounts/backend_dashboard.html` |
| `accounts/certification_home.html` |
| `accounts/district_lms_interop.html` |
| `accounts/entity_console.html` |
| `accounts/import_hub.html` |
| `accounts/migration_wizard.html` |
| `accounts/rbac_dashboard.html` |
| `accounts/security_trust_hub.html` |
| `accounts/tenant_impersonation_audit.html` |
| `accounts/workflow_center.html` |
| `admin/admin_dashboard.html` |
| `analytics/at_risk_dashboard.html` |
| `analytics/dashboard.html` |
| `analytics/executive_dashboard.html` |
| `apicenter/dashboard.html` |
| `compliance/dashboard.html` |
| `customersuccess/super_dashboard.html` |
| `emis/dashboard.html` |
| `evals/compliance_dashboard.html` |
| `finance/dashboard.html` |
| `finance/invoices.html` |
| `marketplace/app_catalog.html` |
| `marketplace/governance_console.html` |
| `marketplace/incident_dashboard.html` |
| `marketplace/installation_health.html` |
| `marketplace/package_rollout.html` |
| `marketplace/sandbox_inspector.html` |
| `metadata/lineage_graph.html` |
| `observability/platform_incidents.html` |
| `observability/slo_dashboard.html` |
| `parent/dashboard.html` |
| `payroll/dashboard.html` |
| `people/employer_dashboard.html` |
| `requests/dashboard.html` |
| `schoolops/ops_library.html` |
| `schools/billing_dashboard.html` |
| `schools/marketing_funnel_dashboard.html` |
| `schools/parent_tenant_dashboard.html` |
| `schools/super_backlog_unlock_center.html` |
| `schools/super_command_center.html` |
| `schools/super_control_health.html` |
| `schools/super_dashboard.html` |
| `schools/super_dashboard_packs.html` |
| `schools/super_he_pack.html` |
| `schools/super_analytics_overview.html` |
| `schools/super_metadata_catalog.html` |
| `schools/super_migration_cloud.html` |
| `schools/super_native_roster_connectors.html` |
| `schools/super_policy_diff.html` |
| `schools/super_platform_operator_hub.html` |
| `schools/super_pulse.html` |
| `schools/super_runtime_truth_hub.html` |
| `schools/super_support_dashboard.html` |
| `schools/super_tenant_360.html` |
| `schools/super_trust_center.html` |
| `schools/super_wedge_index.html` |
| `schools/super_wedge_operator_detail.html` |
| `siteconfig/console_domains_hub.html` |
| `siteconfig/console_domains_hub_control_plane.html` |
| `siteconfig/feature_control_panel.html` |
| `siteconfig/dashboard_configuration_hub.html` |
| `siteconfig/dashboard_hub.html` |
| `student/learning_home.html` |
| `studio_os/partials/subpages/experience_dashboard_visual_packs.html` |
| `teacher/dashboard.html` |

**Adding a new full-page dashboard:** extend `PHASE7_DASHBOARD_TEMPLATES` and ship one of the three markers above before merge.

---

*Extend **RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md** §3.2.1 only; do not spawn a parallel roadmap.*
