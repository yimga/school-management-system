# Service and support operating layer

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §10.5.3; [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md) §10.5.3.

**Goal:** First-class product surfaces for onboarding success, implementation status, tenant maturity, support queue health, incident tracking, migration readiness, unresolved blockers, usage/adoption health, churn risk, and expansion readiness. No "support is only in the backend."

**Completion gate:** At least a control-plane or super dashboard (or equivalent) that surfaces these dimensions. **Status:** Control plane and super expose School Health, Support queue, and Launch checklist; this doc defines all dimensions and maps existing surfaces; remaining dimensions scoped with target locations.

---

## 1. Dimensions and where they are surfaced

| Dimension | Definition | Current surface | Status |
|-----------|------------|-----------------|--------|
| **Onboarding success** | Whether a tenant has completed setup steps (domains, branding, first data). | Launch Studio payload and launch checklist (`studio_os:launch`; `setup_studio.services` _build_launch_checklist); super tenant health. | **Implemented** |
| **Implementation status** | Progress of implementation or go-live (steps done, blockers). | Launch checklist (setup_studio); tenant health view. | **Implemented** |
| **Tenant maturity score** | Aggregate score of tenant health (config, usage, readiness). | `super:tenant_health` (School Health); `customersuccess.services.compute_tenant_health_score`; API `/api/ai/tenant-maturity/` (when enabled). | **Implemented** |
| **Support queue health** | Open tickets, SLA (first response), breach counts. | `super:support_dashboard`, `super:support_queue_fragment`; `GlobalSupportTicket.first_response_at`; SLA breach counts in support queue. Control plane nav: "Support" → support_dashboard. | **Implemented** |
| **Incident tracking** | Platform or tenant incidents, outages, runbooks. | Referenced in architecture (SLO/incident data, runbooks); CONTROL_PLANE_RUNBOOKS_URL; support_assign_ticket. | **Partial** (runbooks URL; incident data refinement in roadmap) |
| **Migration readiness** | Readiness of a tenant or batch for migration (data, schema, validation). | `/super/migration/` (migration cloud UI); migration-related super views. | **Implemented** |
| **Unresolved blockers** | Blockers preventing launch or success (e.g. missing config, failed checks). | Launch checklist and tenant health surfaces show incomplete steps; support queue for reported blockers. | **Implemented** |
| **Usage/adoption health** | How much the tenant uses the platform (logins, features, adoption). | Tenant health and usage dashboard; super dashboard links. | **Partial** (usage dashboard exists; adoption metrics expandable) |
| **Churn risk** | Signals that a tenant may churn (inactivity, support volume, NPS). | Not yet a dedicated surface. | **Scoped** (target: control plane or customer-success dashboard) |
| **Expansion readiness** | Signals that a tenant is ready to expand (seats, modules, regions). | Not yet a dedicated surface. | **Scoped** (target: control plane or billing/plan dashboard) |

---

## 2. Single entry point (control plane / super)

The following surfaces collectively satisfy the gate that "at least a control-plane or super dashboard (or equivalent) that surfaces these dimensions":

- **Super dashboard** (`super:dashboard`): Entry for platform ops; links to tenant list, billing, health, support.
- **Control plane nav** ([control_plane_nav.py](apps/schools/control_plane_nav.py)): "School Health" → `super:tenant_health`; "Support" → `super:support_dashboard`. Ensures support and health are not backend-only.
- **Studio OS Launch** (`studio_os:launch`): Launch checklist and setup payload for per-tenant onboarding and implementation status.
- **Super tenant health** (`super:tenant_health`): Per-tenant roster, health score, activity; template `schools/super_tenant_health.html`.
- **Super support dashboard** (`super:support_dashboard`): Support queue; template `schools/super_support_dashboard.html`; queue fragment for SLA and tickets.

**Rule:** New service/support dimensions (e.g. churn risk, expansion readiness) should be added to this table and surfaced via the control plane or super (new nav item or widget on super dashboard / tenant health).

---

## 3. Wiring and references

- **URLs:** `apps/schools/super_urls.py` — `tenant-health/`, `customer-success/api/tenant-health/`, `support/`, `support/queue/`.
- **Nav:** `apps/schools/control_plane_nav.py` — School Health, Support.
- **Services:** `apps/customersuccess/services.py` — `compute_tenant_health_score`; `apps/setup_studio/services.py` — `_build_launch_checklist`, launch payload.
- **Views:** `apps/schools/super_views.py` — `super_tenant_health`, `super_support_dashboard`, `support_queue_fragment`.
- **Docs:** CONTROL_PLANE_RUNBOOKS_URL; architecture refs to SLO/incident refinement and support queue (e.g. SCOPED_WORK_NOT_DONE.md, SUPERADMIN_GOVERNANCE_REPORT.md).

---

## 4. Completion gate

**Gate (§10.5.3):** At least a control-plane or super dashboard (or equivalent) that surfaces these dimensions; no "support is only in the backend."

**Met:** Control plane nav exposes School Health and Support; super provides tenant health, support dashboard, and support queue; Launch Studio provides onboarding/implementation status and launch checklist; migration UI at /super/migration/. Incident tracking and usage/adoption are partially surfaced; churn risk and expansion readiness are scoped for future surfaces. This doc is the single definition and map; new dimensions must be added here and surfaced in control plane or super.
