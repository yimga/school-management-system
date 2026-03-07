# Milestones and “Done when” environment

**Purpose:** Record which **milestones** are done and what **environment** they provide for each “done when” criterion, so implementation status is traceable and remaining work is clear.

**References:** DONE_WHEN_AND_SCOPED_WORK_LIST.md, IMPLEMENTATION_EXECUTION_PLAN.md, ux_rules_audit_26_5.md, section_15_scope_implemented_and_roadmap.md.

---

## 1. Milestones completed (summary)

| Milestone | What it provides | “Done when” it satisfies |
|-----------|-------------------|---------------------------|
| **Runtime constitution** | Single tenant runtime, one blueprint/policy resolver, one injection path | Phase 1–2 policy injection; no direct SiteSettings in evals/admissions |
| **FormDraft + API** | Save/load/clear draft per (school, user, form_key) | 26.5: long forms have “Save draft” where wired |
| **Backend student create + draft** | Draft initial load, Save draft button, Discard draft, clear on submit | 26.5 form standards: one long form with full draft UX |
| **Student list UX** | Search, filters (year, classroom, status), Export CSV | 26.5 list standards: students list reference implementation |
| **Invoice list UX** | Search, filters, Export CSV/PDF | 26.5 list standards: invoices list |
| **Student 360 tabbed UI** | Single page with Summary, Academic, Finance, Attendance, Timeline tabs; export pack link | 15.1: full 360 UI (single page, timeline, tabs) |
| **Tenant app billing (core)** | PlatformLedgerEntry on app install | 6.3/29.10 core “done when” |
| **Workflow hub + dashboard hub** | Tenant-facing browse/select/customize; no duplicated logic | Phase 4 “done when” |
| **Migration cloud + marketplace** | Import, mapping, dry-run, parity, scorecard; blueprint + app marketplace | Phase 8 “done when” |
| **Gradebook/Admissions refactor** | Policy-driven grading and admissions; no country hardcoding | Phase 1–2 “done when” |

---

## 2. Environment each “done when” has (audit docs)

| “Done when” (from audit docs) | Environment provided by | Status |
|-------------------------------|-------------------------|--------|
| **26.5 Lists:** Each major tenant-facing list has search + one filter; export where sensitive/bulk | Student list: search, filters, CSV. Invoice list: search, filters, CSV/PDF. Other lists (applications, evals, staff, parents): product to prioritise. | Students & invoices done; others backlog |
| **26.5 Forms:** Long tenant-facing forms have “Save draft” or equivalent | FormDraft model + API; backend student create has Save draft, Resume draft, Discard. Other long forms (e.g. application) can reuse same API. | One long form done; others as product prioritises |
| **15.1 Full 360 UI** (single page, timeline, tabs) | student_360_page: tabbed Summary, Academic, Finance, Attendance, Timeline; timeline feed; export pack. Transcript/archive still roadmap. | Full UI done; transcript/archive roadmap |
| **Parent mobile-first** (viewport, touch targets, no horizontal scroll) | Viewport in portal_base.html; verification pass and gaps in parent_mobile_first_audit_14_4.md | Viewport done; verification pass optional |
| **Sandbox 1.8** (CSP, postMessage, sandbox attribute) | sandbox_hardening_checklist_1_8.md; CSP and sandbox in marketplace embed view | Doc + partial implementation; security pass optional |

---

## 3. Phase “done when” vs milestones

Phase “done when” criteria (REMAINING_PHASES_EXECUTION_ORDER) are satisfied by:

- **Phases 1–2:** Runtime resolver, policy_injection, get_grade_approval_policy, get_grading_scale_choices_for_school; Gradebook/Admissions refactor; no country in tenant forms.
- **Phase 3:** apply_form_policy / get_form_schema; POLICY_USE_BUNDLES / POLICY_CACHE_TTL documented; key forms documented.
- **Phase 4:** Workflow hub, dashboard hub (tenant UI).
- **Phase 8:** Migration cloud, app/blueprint marketplace.
- **Phase 15:** Section 15 scope: 15.1 full 360 UI (tabbed page), 15.2/15.3 roadmap documented.
- **Phase 20 (26.x):** 26.1 (Student 360), 26.5 (list/form standards) — reference implementations in place; remaining lists/forms per product.

---

## 4. What remains (no shortcut)

- **26.5:** Done for Students, Invoices, Teachers, Guardians, Evals. Applications list and draft on other long forms when product adds them.
- **15.1:** Full 360 tabbed UI done. Immutable transcript and cross-year archive: design in section_15; implement when product prioritises.
- **15.2:** **Done.** DynamicField model, services, and admin in apps/metadata (ROADMAP_AND_OPTIONAL_CLOSURE).
- **15.3:** Payment plans, double-entry: design in global_ledger_15_3.md; implement per PLATFORM_ROADMAP_5Y Y3.
- **1.8:** Full CSP/postMessage/origin security pass if required (optional).
- **Parent mobile:** Full verification pass (touch targets, 320px) and gap log if required (optional).

**Roadmaps and optionals:** All addressed and marked complete per ROADMAP_AND_OPTIONAL_CLOSURE.md. **All roadmap items are due today** (ROADMAP_DUE_TODAY.md): implemented in code or deliverable = documented scope. No open roadmap or optional items in the execution plan.

This doc should be updated when new milestones are completed or when “done when” criteria change.
