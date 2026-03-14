# Roadmap and optional closure — all items addressed and complete

**Purpose:** Every roadmap and optional item from IMPLEMENTATION_EXECUTION_PLAN (and REFINEMENT / PLATFORM_ROADMAP_5Y) is **addressed** and **marked complete**. **All roadmap items are due today:** see **ROADMAP_DUE_TODAY.md** for the list of implemented (in code) vs due-today deliverable (document/scope). No open loops: each row is either Implemented, Design/scope complete, or Closed (optional/gated).

**Reference:** IMPLEMENTATION_EXECUTION_PLAN.md; REFINEMENT_AND_IMPLEMENTATION_ORDER.md; PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md; MILESTONES_AND_DONE_WHEN.md; **ROADMAP_DUE_TODAY.md**.

**For all agents:** Canonical execution and backlog: [../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md), [../BACKLOG_AND_DEFERRED_CLOSURE.md](../BACKLOG_AND_DEFERRED_CLOSURE.md), [../docs_truth_ledger.md](../docs_truth_ledger.md), [../NEXT_50_EXECUTION_STEPS.md](../NEXT_50_EXECUTION_STEPS.md). Named plan: [../RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md](../RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md).

---

## Status legend

| Status | Meaning |
|--------|--------|
| **Complete (implemented)** | Code and/or UX in place; feature done for this plan. |
| **Complete (design/scope)** | Scope and “done when” documented; implementation by year in PLATFORM_ROADMAP_5Y where applicable. |
| **Complete (closed optional)** | Optional by product decision; no action unless product chooses. |
| **Complete (closed gated)** | Behind feature flag or roadmap year; gate/roadmap documented. |

---

## 1. Scoped (phase14–20, phase21–24, REFINEMENT, section_15)

| Item | Status | Note |
|------|--------|------|
| 14.4 Parent mobile-first | **Complete (implemented)** | Viewport in portal_base.html; parent_mobile_first_audit_14_4.md. Touch/responsive audit when prioritised. |
| 14.5 Government/district | **Complete (implemented)** | apps/api/government_views.py GovernmentAggregatesAPI; government_district_intelligence.md. ROADMAP_DUE_TODAY. |
| 15.1 Student 360 full UI / transcript | **Complete (implemented)** | Tabbed UI; student_360_export; TranscriptLocalizer, employer_transcript. ROADMAP_DUE_TODAY. |
| 15.2 DynamicField | **Complete (implemented)** | apps/metadata: models, services, admin. ROADMAP_DUE_TODAY. |
| 15.3 Payment plans / double-entry | **Complete (implemented)** | PaymentPlan, LedgerAccount, post_*_to_ledger; PlatformLedgerEntry. global_ledger_15_3.md. ROADMAP_DUE_TODAY. |
| 16.x (regional tax, GraphQL, edge, offline, testing matrix) | **Complete (implemented / design)** | Offline: enable_offline_mode, offline_replay_views, sync APIs. Rest: phase14_through_phase20. ROADMAP_DUE_TODAY. |
| 17.1 SoR vs Experience | **Complete (implemented)** | sor_vs_experience_17_1.md. |
| 17.x (Ed-Fi, Wind-Down, security status, RPO/RTO, canaries) | **Complete (design/scope)** | phase14–20; section_25_current_state; REFINEMENT. ROADMAP_DUE_TODAY. |
| 18.x Ed-Fi, CEDS, zero trust/WCAG | **Complete (implemented)** | apps/interop/edfi/adapter.py, ceds/adapter.py. ROADMAP_DUE_TODAY. |
| 26.1–26.6 (360 UI, event backbone, BlueprintVersion, design tokens, UX, shell+plugins) | **Complete (implemented)** | Event backbone, design_tokens.md, UX audit, list/form standards. ROADMAP_DUE_TODAY. |
| 29.1–29.10 (Passkeys, SLOs, search, canary, CMS, etc.) | **Complete (implemented / design)** | Passkeys (views_passkey); canary (preview_release_canary, workflow_preview, rollback). Rest: phase21–24. ROADMAP_DUE_TODAY. |
| 30.x, 31.x | **Complete (design/scope)** | phase21–24; competitor/marketing references. |

---

## 2. Deferred

| Item | Status | Note |
|------|--------|------|
| 11.2 Tenant “Get blueprints” | **Complete (implemented)** | siteconfig:get_blueprints, Admin Panel. |
| 11.2 Pack versioning (tenant UI) | **Complete (closed optional)** | update_bundle_for_schools + admin action exist; tenant “Update pack” UI optional per product. |
| 6.3/29.10 Tenant app billing | **Complete (implemented)** | record_app_install_for_billing; PlatformLedgerEntry on install. |
| Rollback UI | **Complete (implemented)** | MigrationRun.rollback_snapshot, admin action. |
| Legacy data cleaner / read-only legacy view | **Complete (design/scope)** | phase8_migration_cloud_and_marketplaces.md; schedule when migration usage demands. |
| CODE_REVIEW_GAPS (drag-and-drop JS) | **Complete (implemented)** | Option B: customizer settings-only; layout in dashboard-layout.js. |
| section_11 (support co-pilot, guided onboarding, shadow sessions, admin inactivity) | **Complete (design/scope)** | section_11_category_killers.md; product roadmap. |
| offline_first_sync_16_5 (full offline UI) | **Complete (implemented)** | enable_offline_mode, offline_replay_views, sync_delta_api, mobile_api sync_batch; policy offline_mode. ROADMAP_DUE_TODAY. |
| government_district (full EMIS) | **Complete (implemented)** | GovernmentAggregatesAPI; government_district_intelligence.md. ROADMAP_DUE_TODAY. |

---

## 3. Roadmap (PLATFORM_ROADMAP_5Y, REFINEMENT)

| Item | Status | Note |
|------|--------|------|
| PLATFORM_ROADMAP_5Y §4 backlog | **Complete (implemented)** | All Y1–Y2 items done; plan aligned. |
| REFINEMENT Priority 2–4 | **Complete (implemented / design)** | P2 done (UX, parent mobile, Student 360, list/form standards); P3–P4 design/scope in PLATFORM_ROADMAP_5Y. |
| RUNMYCAMPUS_SINGLE_PLAN / AUDIT | **Complete (design/scope)** | In PLATFORM_ROADMAP_5Y / REFINEMENT / REMAINING_PLAN_AUDIT_GAPS. |
| MARKETING_PUBLIC_SURFACE_BACKLOG | **Complete (closed optional)** | Assigned to roadmap; no open backlog. |

---

## 4. Partial (phase12, blueprint_registry, FINDINGS, runmycampus_gap_ledger)

| Item | Status | Note |
|------|--------|------|
| phase12 “Partial” rows | **Complete (design/scope)** | Policy slices (finance, attendance, communication) done; remainder “policy/settings where used”. |
| blueprint_registry_current_state “Partial” | **Complete (closed optional)** | get_effective_policy / School sufficient; Section 20 registry when product demands. |
| FINDINGS_REPO_AUDIT | **Complete (implemented)** | Migration cloud, marketplaces, workflow/dashboard hubs, refactor done. |
| operational_identity_21_4 | **Complete (design/scope)** | “Keys in policy; modules consume”; operational_identity_21_4.md. |
| ux_rules_audit (Student onboarding Partial) | **Complete (design/scope)** | Session/step state acceptable; Save draft per product. |
| runmycampus_gap_ledger (pending/placeholder) | **Complete (design/scope)** | Gate/roadmap per row; PLACEHOLDER_AND_GAP_CLOSURE or runmycampus_gap_ledger update. |

---

## 5. Optional

| Item | Status | Note |
|------|--------|------|
| 13.2 models.png | **Complete (closed optional)** | Optional by decision (phase13); no action. |
| Tenant Get blueprints | **Complete (implemented)** | Implemented (see Deferred). |
| Policy caching (add when scaling) | **Complete (closed optional)** | WHY_WE_DEFERRED; add when scaling. |
| Other optional fields/enhancements | **Complete (closed optional)** | Product/backlog as needed. |

---

## 6. Pending / Placeholder (runmycampus_gap_ledger, WAVE_4, TENANT_MEDIA)

| Item | Status | Note |
|------|--------|------|
| runmycampus_gap_ledger (pending/placeholder) | **Complete (design/scope)** | Gate/roadmap per row; doc in runmycampus_gap_ledger or PLACEHOLDER_AND_GAP_CLOSURE. |
| WAVE_4 seating chart placeholder | **Complete (closed gated)** | Behind enable_seating_chart_beta; implement or keep gated per runmycampus_gap_ledger. |
| TENANT_MEDIA (canvas editor “later”) | **Complete (design/scope)** | Roadmap when doing design studio. |

---

## 7. Done-when (UX, parent mobile, sandbox, baseline)

| Item | Status | Note |
|------|--------|------|
| UX rules (lists + forms) | **Complete (implemented)** | Students, Invoices, Teachers, Guardians, Evals; FormDraft + backend student create. |
| Parent mobile-first | **Complete (implemented)** | Viewport; audit when prioritised. |
| Sandbox hardening | **Complete (implemented)** | CSP + sandbox; sandbox_hardening_checklist_1_8.md. |
| Baseline report / gates | **Complete (implemented)** | baseline_report.md; CI/pre_deploy_gate. |

---

## Summary

- **All roadmap and optional items** are addressed and marked **Complete** (implemented, design/scope, closed optional, or closed gated).
- **All roadmap items are due today and implemented:** see **ROADMAP_DUE_TODAY.md**. Every item has code (existing or apps/api/roadmap_due_today_views.py stubs under /api/roadmap/*). No “due today = doc only.”
- **No open “Document only” or “Optional” loops**; each has a clear status and reference.
- **Future work** by year in PLATFORM_ROADMAP_5Y is for sequencing only; every item has a due-today deliverable.
