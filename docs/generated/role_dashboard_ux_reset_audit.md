# Role dashboard UX reset audit (Agent 3)

Canonical product checklist: `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`. This file is an implementation audit table only.

| Dashboard | Template | Primary user | Current clutter (before reset) | Missing next action | Passive metrics | Duplicate CTAs | Empty-state weakness | New page name | Required sections | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tenant admin / backend | `templates/accounts/backend_dashboard.html` | School admin / operator | Large hero, many strips, intent pills | Not surfaced as one strip | KPI grid without narrative | Overview CTAs + role home CTAs | Hidden modules message thin | **School Command Center** | Today ops, readiness, what needs attention, next action, money/academic trust | P0 |
| Super founder | `templates/super/founder_dashboard.html` | Platform founder / operator | Long metric grid, mixed concerns | Action strip not grouped | Many equal cards | Pipeline in header + section | Audit missing text OK | **Platform Command Center** | System pulse, growth, money, ops queue, latest proof, one next action | P0 |
| Teacher | `templates/teacher/dashboard.html` | Teacher | Insights before day plan | Single hero CTA only | Stats without “plan” label | Fast workflows + hero | No classes alert OK | **My Teaching Day / Teacher workspace** | Today plan, one next action, my classes, pending work, signals, offline | P0 |
| Parent | `templates/parent/dashboard.html` | Guardian | Many glance tiles | Workflow vs finance competing | Glance grid | Header + quick actions | No child linked | **Family Home** | Family summary, one next action, child cards, money, reports, help | P0 |
| Finance | `templates/finance/dashboard.html` | Finance staff | Hero + charts | Primary was not rendered (bar partial) | Chart grid | Many outline buttons | Empty invoices | **Money Center** (workspace) | What needs attention, primary money action, widgets | P1 |
| Analytics | `templates/analytics/dashboard.html` | Admin / principal | KPI grid buried | Primary governed report | Dense KPI | Old dual header pattern | — | **Insights Center** | What needs attention, primary report build, drill-down optional | P1 |
| Tenant lifecycle | `templates/platform_runtime/tenant_lifecycle_dashboard.html` | Platform / hub-eligible admin | Long lists | Primary per row | Cohort rates | — | Insufficient cohort | **Tenant lifecycle portfolio** | System pulse, cohorts, at-risk / expansion, adoption | P1 |

Implementation markers: `data-rmc-ux-role-dashboard`, `data-rmc-ux-section` (`what-needs-attention`, `school-readiness`, `today-operations`, `system-pulse`, `today-plan`, `family-summary`, etc.), and `<!-- rmc-ux-above-fold-end -->` for strict primary checks.
