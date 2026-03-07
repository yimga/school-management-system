# Backlog — all items addressed

**Purpose:** Record that all backlog items from the execution plan have been addressed (implemented or explicitly documented with owner/year). No open “to do” left without a decision.

**References:** IMPLEMENTATION_EXECUTION_PLAN.md, MILESTONES_AND_DONE_WHEN.md, ux_rules_audit_26_5.md.

---

## Addressed in this pass

| Category | Item | Resolution |
|----------|------|------------|
| **To do** | CODE_REVIEW_GAPS (drag-and-drop JS) | **Done:** Option B — `dashboard-customizer.js` is settings-only; drag/reorder only in `dashboard-layout.js`. |
| **26.5 lists** | Staff (teachers) | **Done:** Search, department filter, Export CSV on backend teacher list. |
| **26.5 lists** | Parents/guardians | **Done:** Backend guardian list with search, year/classroom filter, Export CSV (`/backend/guardians/`). |
| **26.5 lists** | Applications | Document only: when admissions module provides an application list, add search/filter/export per same pattern. |
| **26.5 forms** | Application form draft | No long application form in codebase; add FormDraft when product adds one. |
| **Ongoing** | Baseline report / CI gates | baseline_report.md and pre_deploy_gate; backlog note in §8 execution plan. |
| **Roadmap** | DynamicField, ledger, Ed-Fi, etc. | Documented in MILESTONES_AND_DONE_WHEN §4 “What remains” and PLATFORM_ROADMAP_5Y by year. |

---

## Summary

- **Done:** CODE_REVIEW_GAPS Option B; Teacher list CSV; Guardian list (new view + CSV); UX audit and execution plan updated.
- **Document only:** Applications list, application form draft, roadmap items — owner/year in REFINEMENT and PLATFORM_ROADMAP_5Y.
- **Ongoing:** Baseline/CI as in baseline_report.md.

Nothing remains in the backlog as an unaddressed “to do”; everything is either implemented or explicitly scoped to roadmap/product.
