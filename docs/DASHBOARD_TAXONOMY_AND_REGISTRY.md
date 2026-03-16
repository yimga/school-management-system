# Dashboard taxonomy and registry

**Purpose:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §10.5.5 and [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md). Every dashboard is declared and governed so it is not a junk drawer.

**Authority:** This doc is the dashboard registry. New or materially changed dashboards must declare the required fields below before merge. Completion gate: taxonomy doc exists; all existing critical dashboards registered; new dashboards must declare before merge.

---

## Required declarations per dashboard

| Field | Description |
|-------|-------------|
| **User** | Primary user/role (e.g. operator, school admin, teacher, parent, super) |
| **Job-to-be-done** | Primary job (e.g. "See tenant health", "Manage workflows") |
| **Dashboard type** | Strategic / operational / analytical |
| **Primary question answered** | What the user is asking |
| **Primary action enabled** | Main CTA or next-best-action |
| **Update frequency** | Real-time / on-load / scheduled / on-demand |
| **Drill-down path** | Where user goes for detail |
| **Alerting behavior** | What triggers alerts or warnings |

---

## Registry of critical dashboards

### Tenant / school context

| Name / route | User | Job-to-be-done | Type | Primary question | Primary action | Update | Drill-down | Alerting |
|--------------|------|-----------------|------|-------------------|----------------|--------|------------|----------|
| `accounts:backend_dashboard` | Authenticated staff | Role home / next action | Operational | "Where do I go next?" | Role-resolved CTA (Studio, Operations, etc.) | On-load | Studio OS modes, portal, workflows | — |
| `portal:parent_dashboard` | Parent | Child overview and actions | Operational | "How are my children?" | View results, fees, attendance | On-load | Child detail, document library | — |
| `organization_network_dashboard` | Parent (org) | Network/organization view | Analytical | "What is my org status?" | Navigate org | On-load | — | — |

### Studio OS (unified shell)

| Name / route | User | Job-to-be-done | Type | Primary question | Primary action | Update | Drill-down | Alerting |
|--------------|------|-----------------|------|-------------------|----------------|--------|------------|----------|
| `studio_os:experience` | Operator / admin | Theme and experience | Operational | "What is the experience setup?" | Edit theme, feature control | On-load | Experience pack, theme colors | — |
| `studio_os:automation` | Operator / admin | Workflows and automation | Operational | "What workflows are running?" | Run / configure workflow | On-load | Workflow hub, outcomes console | — |
| `studio_os:output` | Operator / admin | Reports and documents | Operational | "What reports/documents exist?" | Preview, publish, rollback | On-load | Report library, document library | — |
| `studio_os:launch` | Operator / admin | Launch and setup | Operational | "Is the school ready to launch?" | Run checklist, create school | On-load | Launch checklist, health | — |
| `studio_os:control` | Operator / admin | Control and config | Operational | "What is the system state?" | Runtime inspector, domains, config | On-load | Console domains, runtime inspector | — |

### Super / control plane

| Name / route | User | Job-to-be-done | Type | Primary question | Primary action | Update | Drill-down | Alerting |
|--------------|------|-----------------|------|-------------------|----------------|--------|------------|----------|
| `super:dashboard` | Super / platform ops | Tenant and platform health | Strategic | "How is the platform?" | Drill into tenant, billing | On-load | Tenant list, billing_dashboard | — |
| `super:billing_dashboard` | Super / finance | Billing and plans | Operational | "What is billing status?" | Manage plan, view usage | On-load | Tenant billing detail | — |

### Observability and admin

| Name / route | User | Job-to-be-done | Type | Primary question | Primary action | Update | Drill-down | Alerting |
|--------------|------|-----------------|------|-------------------|----------------|--------|------------|----------|
| `admin_dashboard` (observability) | Staff / admin | System health and charts | Operational | "How is the system performing?" | View charts, SLO | On-load / API | api_dashboard_charts, SLO dashboard | — |
| `api_operational_slo_dashboard` | Staff / admin | SLO and ops metrics | Analytical | "Are SLOs met?" | View SLO metrics | On-demand / API | — | SLO breach |

### Marketing

| Name / route | User | Job-to-be-done | Type | Primary question | Primary action | Update | Drill-down | Alerting |
|--------------|------|-----------------|------|-------------------|----------------|--------|------------|----------|
| `marketing_funnel_dashboard` | Marketing / ops | Funnel and conversion | Analytical | "How is the funnel?" | View funnel metrics | On-load / scheduled | — | — |

---

## Adding or changing a dashboard

1. Add a row to the appropriate table above (or a new section if a new category).
2. Fill all required fields (user, job-to-be-done, type, primary question, primary action, update frequency, drill-down, alerting).
3. Ensure the dashboard aligns with the decision architecture (seven questions) in [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md) §1.8/§8.0.
4. Update this registry in the same PR as the dashboard change.

---

## Status

- **Taxonomy and registry:** This doc. All critical dashboards listed above are registered.
- **New dashboards:** Must declare before merge (add row here + seven-question alignment).
- **Existing dashboards not yet listed:** Add as they are touched or during Phase I rollout.
