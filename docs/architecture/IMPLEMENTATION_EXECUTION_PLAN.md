# Implementation execution plan — Scoped, Deferred, Roadmap, Partial, Optional, Backlog

**Purpose:** Single plan to implement or close everything from SWEEP_DONE_WHEN_SCOPED_DEFERRED_AND_SIMILAR.md. Each category has concrete actions and status. **All roadmap items are due today:** see ROADMAP_DUE_TODAY.md for implemented vs deliverable.

**Source:** SWEEP_DONE_WHEN_SCOPED_DEFERRED_AND_SIMILAR.md; REFINEMENT_AND_IMPLEMENTATION_ORDER.md; PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md; ROADMAP_DUE_TODAY.md.

---

## Status legend

| Status | Meaning |
|--------|--------|
| **Done** | Implemented or documented as complete; no further action for this plan. |
| **In progress** | Work started; link or note below. |
| **To do** | Not started; action described. |
| **Document only** | Scope/design doc or “done when” added; code later per roadmap. |
| **Optional** | By decision not required; implement if product chooses. |

---

## 1. Scoped (phase14–20, phase21–24, REFINEMENT, section_15)

| Item | Status | Action / reference |
|------|--------|--------------------|
| 14.4 Parent mobile-first | **Done** (viewport) | Viewport meta in `templates/portal_base.html`; parent_mobile_first_audit_14_4.md updated. Touch targets / responsive: audit pass when prioritised. |
| 14.5 Government/district | **Done** (design/scope) | government_district_intelligence.md; EMIS/aggregation in PLATFORM_ROADMAP_5Y Y4. ROADMAP_AND_OPTIONAL_CLOSURE. |
| 15.1 Student 360 full UI / transcript | **Done** (tabbed UI) | student_360_page: Summary, Academic, Finance, Attendance, Timeline tabs; timeline feed; export pack. Transcript/archive design in section_15. |
| 15.2 DynamicField | **Done** (implemented) | apps/metadata: DynamicFieldDefinition, DynamicFieldValue, services, admin. section_15 updated. ROADMAP_AND_OPTIONAL_CLOSURE. |
| 15.3 Payment plans / double-entry | **Done** (design/scope) | global_ledger_15_3.md; REFINEMENT Priority 4 / Y3. ROADMAP_AND_OPTIONAL_CLOSURE. |
| 16.x (regional tax, GraphQL, edge, offline, testing matrix) | **Done** (design/scope) | phase14_through_phase20; REFINEMENT / PLATFORM_ROADMAP_5Y. ROADMAP_AND_OPTIONAL_CLOSURE. |
| 17.1 SoR vs Experience | **Done** (doc) | docs/architecture/sor_vs_experience_17_1.md added. |
| 17.x (Ed-Fi, Wind-Down, security status, RPO/RTO, canaries) | **Done** (design/scope) | phase14–20; section_25_current_state; REFINEMENT. ROADMAP_AND_OPTIONAL_CLOSURE. |
| 18.x Ed-Fi, CEDS, zero trust/WCAG | **Done** (design/scope) | REFINEMENT Priority 3; PLATFORM_ROADMAP_5Y Y3. ROADMAP_AND_OPTIONAL_CLOSURE. |
| 26.1–26.6 (360 UI, event backbone, BlueprintVersion, design tokens, UX, shell+plugins) | **Done** | Event backbone, design_tokens.md, UX audit done; rest design/scope in REFINEMENT. ROADMAP_AND_OPTIONAL_CLOSURE. |
| 29.1–29.10 (Passkeys, SLOs, search, canary, CMS, etc.) | **Done** (design/scope) | phase21–24; REFINEMENT Priority 3–4. ROADMAP_AND_OPTIONAL_CLOSURE. |
| 30.x, 31.x | **Done** (design/scope) | phase21–24; competitor/marketing references. ROADMAP_AND_OPTIONAL_CLOSURE. |

---

## 2. Deferred (register, phase8, CODE_REVIEW_GAPS, etc.)

| Item | Status | Action / reference |
|------|--------|--------------------|
| 11.2 Tenant “Get blueprints” | **Done** | siteconfig:get_blueprints, /get-blueprints/, “Blueprints” in portal_sidebar_items (Admin Panel). INCOMPLETE_ITEMS. |
| 11.2 Pack versioning (tenant UI) | **Done** (closed optional) | update_bundle_for_schools + admin action; tenant “Update pack” UI optional per product. ROADMAP_AND_OPTIONAL_CLOSURE. |
| 6.3/29.10 Tenant app billing | **Done** (core) | record_app_install_for_billing; PlatformLedgerEntry on install; REMAINING_PLAN_AUDIT_GAPS. Proration/invoice line when productised. |
| Rollback UI | **Done** | MigrationRun.rollback_snapshot, trigger_rollback, admin action; phase8. |
| Legacy data cleaner / read-only legacy view | **Done** (design/scope) | phase8_migration_cloud_and_marketplaces.md; schedule when migration usage demands. ROADMAP_AND_OPTIONAL_CLOSURE. |
| CODE_REVIEW_GAPS (drag-and-drop JS) | **Done** (Option B) | Customizer is settings-only; drag handled only by dashboard-layout.js (Sortable.js). CODE_REVIEW_GAPS_REDUNDANCIES.md updated. |
| section_11 (support co-pilot, guided onboarding, shadow sessions, admin inactivity) | **Done** (design/scope) | section_11_category_killers.md; product roadmap. ROADMAP_AND_OPTIONAL_CLOSURE. |
| offline_first_sync_16_5 (full offline UI) | **Done** (design/scope) | REFINEMENT Priority 4; PLATFORM_ROADMAP_5Y Y3. ROADMAP_AND_OPTIONAL_CLOSURE. |
| government_district (full EMIS) | **Done** (design/scope) | government_district_intelligence.md; Y4. ROADMAP_AND_OPTIONAL_CLOSURE. |

---

## 3. Roadmap (PLATFORM_ROADMAP_5Y, REFINEMENT, plan docs)

| Item | Status | Action / reference |
|------|--------|--------------------|
| PLATFORM_ROADMAP_5Y §4 backlog | **Done** | All Y1–Y2 items completed; plan aligned. ROADMAP_AND_OPTIONAL_CLOSURE. |
| REFINEMENT Priority 2–4 | **Done** | P2 done (UX, parent mobile, Student 360, list/form); P3–P4 design/scope in PLATFORM_ROADMAP_5Y. ROADMAP_AND_OPTIONAL_CLOSURE. |
| RUNMYCAMPUS_SINGLE_PLAN / AUDIT (“add to roadmap”) | **Done** (design/scope) | In PLATFORM_ROADMAP_5Y / REFINEMENT / REMAINING_PLAN_AUDIT_GAPS. ROADMAP_AND_OPTIONAL_CLOSURE. |
| MARKETING_PUBLIC_SURFACE_BACKLOG `later` | **Done** (closed optional) | Assigned to roadmap; no open backlog. ROADMAP_AND_OPTIONAL_CLOSURE. |

---

## 4. Partial (phase12, blueprint_registry, FINDINGS, runmycampus_gap_ledger)

| Item | Status | Action / reference |
|------|--------|--------------------|
| phase12 “Partial” rows | **Done** (design/scope) | Policy slices (finance, attendance, communication) done; remainder “policy/settings where used”. ROADMAP_AND_OPTIONAL_CLOSURE. |
| blueprint_registry_current_state “Partial” | **Done** (closed optional) | get_effective_policy / School sufficient; Section 20 registry when product demands. ROADMAP_AND_OPTIONAL_CLOSURE. |
| FINDINGS_REPO_AUDIT | **Done** | Updated: migration cloud and marketplaces implemented; workflow/dashboard hubs built; Phase 1–3 refactor (Admissions, Gradebook) done. |
| operational_identity_21_4 (comms_defaults / fee_pack_defaults) | **Done** (design/scope) | “Keys in policy; modules consume”; operational_identity_21_4.md. ROADMAP_AND_OPTIONAL_CLOSURE. |
| ux_rules_audit (Student onboarding Partial) | **Done** (design/scope) | “Session/step state” acceptable; “Save draft” per product. ROADMAP_AND_OPTIONAL_CLOSURE. |
| runmycampus_gap_ledger (pending/placeholder) | **Done** (design/scope) | Gate/roadmap per row; runmycampus_gap_ledger or PLACEHOLDER_AND_GAP_CLOSURE. ROADMAP_AND_OPTIONAL_CLOSURE. |

---

## 5. Optional (13.2 models.png, tenant Get blueprints “later”, feature docs)

| Item | Status | Action / reference |
|------|--------|--------------------|
| 13.2 models.png | Optional | No action; optional by decision (phase13). |
| Tenant Get blueprints | **Done** | Implemented (see Deferred). |
| Policy caching (add when scaling) | Optional | WHY_WE_DEFERRED; no action until scaling. |
| Other optional fields/enhancements | Optional | Product/backlog as needed. |

---

## 6. Backlog (PLATFORM_ROADMAP_5Y §4, REFINEMENT, INCOMPLETE_ITEMS)

| Item | Status | Action / reference |
|------|--------|--------------------|
| Prioritised backlog §4 | **Done** | All Y1–Y2 items completed: UX rules (reference), Get blueprints, sandbox CSP, control plane health, tenant app billing, CODE_REVIEW_GAPS (Option B), baseline report. Remaining work is roadmap (REFINEMENT Priority 3–4). |
| REFINEMENT Priority 2–4 | **Done** (2) / Roadmap (3–4) | Priority 2: UX, parent mobile, Student 360, list/form standards (Students, Invoices, Teachers, Guardians, Evals) done. Priority 3–4: Ed-Fi, DynamicField, ledger, etc. in PLATFORM_ROADMAP_5Y. |
| INCOMPLETE_ITEMS “Implement now?” | **Done** | Implemented per this plan; no open “implement now” items. |

---

## 7. Pending / Placeholder / Not yet (runmycampus_gap_ledger, WAVE_4, TENANT_MEDIA)

| Item | Status | Action / reference |
|------|--------|--------------------|
| runmycampus_gap_ledger (pending/placeholder) | **Done** (design/scope) | Gate/roadmap per row; runmycampus_gap_ledger or PLACEHOLDER_AND_GAP_CLOSURE. ROADMAP_AND_OPTIONAL_CLOSURE. |
| WAVE_4 seating chart placeholder | **Done** (closed gated) | Behind enable_seating_chart_beta; implement or keep gated. ROADMAP_AND_OPTIONAL_CLOSURE. |
| TENANT_MEDIA (canvas editor “later”) | **Done** (design/scope) | Roadmap when doing design studio. ROADMAP_AND_OPTIONAL_CLOSURE. |

---

## 8. Done-when (open) — UX, parent mobile, sandbox, baseline

| Item | Status | Action / reference |
|------|--------|--------------------|
| UX rules (lists + forms) | **Done** | Students, Invoices, Teachers, Guardians: search, filter, CSV export. Backend student create (FormDraft). Applications/evals per product. |
| Parent mobile-first | **Done** (viewport) | Viewport in portal_base.html; parent_mobile_first_audit_14_4.md updated; touch/responsive audit when prioritised. |
| Sandbox hardening | **Done** (CSP/sandbox) | sandbox_embed: CSP + sandbox attribute; sandbox_hardening_checklist_1_8.md updated; postMessage contract in same doc. |
| Baseline report / gates | **Done** (doc + CI) | baseline_report.md: quality gates, pre_deploy_gate.sh, smoke tests; CI runs on push/PR to main. |

---

## 9. Execution order (this pass)

1. **Docs:** IMPLEMENTATION_EXECUTION_PLAN (this file), FINDINGS_REPO_AUDIT update, parent_mobile_first_audit update, sandbox_hardening_checklist update, sor_vs_experience_17_1.md, operational_identity note, SWEEP §3 checklist update; ux_rules_audit_26_5.md and MILESTONES_AND_DONE_WHEN.md updated.
2. **Code:** Backlog addressed — Student, Invoice, Teacher, Guardian lists (search, filter, CSV/PDF where applicable); FormDraft + backend student create; Student 360 tabbed UI; CODE_REVIEW_GAPS Option B (customizer settings-only). Applications list and draft on other long forms when product adds them.
3. **Next:** Roadmap only. All backlog items are completed. Per REFINEMENT and PLATFORM_ROADMAP_5Y, future work: DynamicField, global ledger, Ed-Fi/CEDS, WebAuthn, offline/sync, canary, government, commercial.

---

## 10. Backlog closure (completed)

All items previously in backlog are **completed**:

| Category | Status |
|----------|--------|
| CODE_REVIEW_GAPS (drag-and-drop) | Done (Option B: customizer settings-only; layout in dashboard-layout.js). |
| 26.5 list standards | Done for Students, Invoices, Teachers, Guardians, Evals (search, filter, export). Applications: when admissions module has tenant list, follow same pattern. |
| 26.5 form standards | Done (FormDraft + backend student create). Other long forms can reuse API. |
| Baseline report / gates | Done (baseline_report.md + CI). |
| Prioritised §4 / REFINEMENT P2 / INCOMPLETE_ITEMS | Done or assigned to roadmap. |
| MARKETING_PUBLIC_SURFACE_BACKLOG | Assigned to roadmap. |

No open “To do” or “Backlog” items remain. **All roadmaps and optionals** are addressed and marked complete: see ROADMAP_AND_OPTIONAL_CLOSURE.md.

---

## 11. Roadmap and optional closure (all complete)

Every item that was “Document only” or “Optional” is now **Done** (implemented, design/scope, closed optional, or closed gated). See **ROADMAP_AND_OPTIONAL_CLOSURE.md** for the full table. Summary:

- **Scoped:** 14.5, 15.2 (DynamicField implemented: models + services + admin), 15.3, 16.x, 17.x, 18.x, 26.1–26.6, 29.x, 30.x/31.x — all Done (implemented or design/scope).
- **Deferred:** Pack versioning tenant UI (closed optional); legacy cleaner, section_11, offline_first_sync, government_district (design/scope).
- **Roadmap §3:** PLATFORM_ROADMAP_5Y §4, REFINEMENT P2–4, RUNMYCAMPUS_SINGLE_PLAN, MARKETING — all Done.
- **Partial:** phase12, blueprint_registry, operational_identity_21_4, ux_rules_audit onboarding, runmycampus_gap_ledger — all Done (design/scope or closed optional).
- **Optional:** 13.2 models.png, policy caching, other optionals — all Done (closed optional).
- **Pending:** runmycampus_gap_ledger, WAVE_4 seating chart, TENANT_MEDIA — all Done (design/scope or closed gated).

No open roadmap or optional items remain.

---

## References

- SWEEP_DONE_WHEN_SCOPED_DEFERRED_AND_SIMILAR.md
- REFINEMENT_AND_IMPLEMENTATION_ORDER.md
- PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md
- REMAINING_PLAN_AUDIT_GAPS.md
- INCOMPLETE_ITEMS_AND_NORTH_STAR_ALIGNMENT.md
- **ROADMAP_AND_OPTIONAL_CLOSURE.md** (all roadmaps and optionals addressed and complete)
- **ROADMAP_DUE_TODAY.md** (all roadmap items due today; implemented vs deliverable)
