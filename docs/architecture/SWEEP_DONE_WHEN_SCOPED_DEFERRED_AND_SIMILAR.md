# Sweep: “Done when”, scoped, deferred, save-for-later, and similar

**Purpose:** One sweep through codebase docs for every use of **done when**, **scoped**, **deferred**, **save for later**, **roadmap**, **partial**, **optional**, **backlog**, **pending**, **placeholder**, and similar. Use this to decide what to do next.

**Date:** 2026-03-06

---

## 1. Terminology used in the docs

| Term | Meaning in this codebase | Typical location |
|------|---------------------------|-------------------|
| **Done when** | Completion criterion for a phase or item; “phase is complete when …” | REMAINING_PHASES_EXECUTION_ORDER, audit docs (UX, parent mobile, sandbox), baseline_report, section_28 |
| **Scoped** | Work is defined and bounded; implementation is later or partial | phase14–20, phase21–24, REFINEMENT, section_25_current_state, PLATFORM_ROADMAP_5Y |
| **Deferred** | Explicitly postponed; “done later” or “when needed” | REMAINING_PHASES, phase8, RUNMYCAMPUS consolidated (Deferred and optional register), WHY_WE_DEFERRED, CODE_REVIEW_GAPS, REDUNDANCY_AND_PLAN_INDEX |
| **Roadmap** | Planned for a future year or “when we get to it”; not deferred without a plan | PLATFORM_ROADMAP_5Y, REFINEMENT, section_15_scope, government_district_intelligence, PART_G_STANDARDS, RUNMYCAMPUS_SINGLE_PLAN_COMPLETE |
| **Partial** | Partly implemented; remainder is the “next step” | phase12, phase14–20, phase21–24, REFINEMENT, blueprint_registry_current_state, FINDINGS_REPO_AUDIT, ux_rules_audit, runmycampus_gap_ledger |
| **Optional** | By decision not required for completion; “nice to have” or “add when needed” | RUNMYCAMPUS consolidated (13.2 models.png), phase8 (tenant Get blueprints “optional later”), many feature docs (optional fields, optional enhancements) |
| **Backlog** | Prioritised list of work to pull into sprints | PLATFORM_ROADMAP_5Y §4, REFINEMENT, INCOMPLETE_ITEMS, MARKETING_PUBLIC_SURFACE_BACKLOG |
| **Save for later** | Not used as a phrase; equivalent = “deferred”, “roadmap”, “optional” | — |
| **Pending** | Used for status (e.g. pending approval, pending sync); sometimes “not yet implemented” | runmycampus_gap_ledger, AUTOMATION_PLAN_FINAL, PHASE_8_INDEX |
| **Placeholder** | UI or surface exists but not full implementation; “coming soon” or stub | WAVE_4_TASKS (seating chart), TENANT_MEDIA_AND_DESIGN_STUDIO, runmycampus_gap_ledger, ux (chat widget) |
| **Not yet** | Explicitly not implemented | Various (“not yet implemented”, “not yet fully”) |
| **Later** | “Can be done later”, “add later”, “revisit later” | DASHBOARD_AND_ADMIN_MASTER_PLAN, CODE_REVIEW_GAPS, THEME_OPTIONS_REVISITED, MARKETING_PUBLIC_SURFACE_BACKLOG (`later` queue) |

---

## 2. By category — where it appears and what to do next

### 2.1 “Done when” (completion criteria)

| Source | Item | Status | What to do next |
|--------|------|--------|------------------|
| REMAINING_PHASES_EXECUTION_ORDER | Phases 1–24 “Done when” bullets | All [x] | No action; use as reference only. |
| ux_rules_audit_26_5.md | Lists: search + filter + export; Forms: draft/autosave | [x] ref | Done: document library CSV; applicants list; application form Save draft. Deferred: classes/sections; onboarding step-level draft. See SCOPED_WORK_VERIFICATION.md. |
| parent_mobile_first_audit_14_4.md | Viewport + touch + no horizontal scroll on key parent pages | [x] | Verified per checklist; see SCOPED_WORK_VERIFICATION.md. |
| sandbox_hardening_checklist_1_8.md | CSP + embed points + postMessage + sandbox attribute | [x] | CSP, sandbox attribute, origin validation in sandbox_embed; see SCOPED_WORK_VERIFICATION.md. |
| baseline_report.md | Baseline report exists; all gates green; release checklist skeleton | [x] | Done: baseline_report.md + Verification table; pre_deploy_gate.sh; smoke.yml; RELEASE_CHECKLIST.md. |
| section_28_data_architecture_and_provisioning.md | 28.1–28.9 “Done when” (documentation) | [x] | No action. |
| THREE_PLANS / W0-4 | Baseline report published; gates green on main | Tracked in plan | Same as baseline_report. |

**Decision aid:** For any “[ ]” “Done when”, either (a) implement until the criterion is met, or (b) explicitly move to “scoped/roadmap” with a target (sprint or year) and owner.

---

### 2.2 “Scoped” (defined, not fully done)

| Source | Item | What to do next |
|--------|------|------------------|
| phase14_through_phase20_sections_14_to_26.md | 14.4 Parent PWA/offline; 14.5 Government; 15.1–15.2 Student 360, DynamicField; 16.x (regional tax, GraphQL, edge, offline, testing matrix); 17.x (SoR/Experience doc, Ed-Fi, Wind-Down, security status, RPO/RTO, canaries); 18.x (Ed-Fi, CEDS, zero trust/WCAG audit); 26.1–26.6 (360 UI, event backbone, BlueprintVersion, design tokens, UX rules checklist, shell+plugins) | Pick by priority from REFINEMENT and PLATFORM_ROADMAP_5Y; implement or document “done when” and owner. |
| phase21_through_phase24_sections_27_to_31.md | 29.1–29.10 (Passkeys, traces/SLOs, control-plane search, preview/canary, CMS, rollback/exception queue, OAuth/monitoring, design tokens, AI guardrails, commercial); 30.x (segmented journeys, win-condition checklist); 31.x (Ed-Fi, CEDS, OpenFeature) | Same: prioritise from REFINEMENT/roadmap; close with implementation or clear “done when”. |
| REFINEMENT_AND_IMPLEMENTATION_ORDER.md | Priority 2: UX rules, parent mobile-first. Priority 3: Ed-Fi, CEDS, WebAuthn. Priority 4: Student 360 UI, DynamicField, global ledger, offline/sync, preview/canary, government, commercial. | **Decide:** Use as sprint backlog; 1–2 items per sprint from Priority 2–4; update checklist when done. |
| section_15_scope_implemented_and_roadmap.md | 15.1 full UI/transcript; 15.2 DynamicField model+UI; 15.3 payment plans/double-entry | Already has “done when” text; schedule implementation by year (see PLATFORM_ROADMAP_5Y). |
| global_ledger_15_3.md | Multi-currency conversion | Scoped | Add when multi-currency conversion is productised. |

**Decision aid:** “Scoped” = work is defined. Next step: assign **owner** and **target (sprint or year)** or mark **optional** and document why.

---

### 2.3 “Deferred” (explicitly postponed)

| Source | Item | What to do next |
|--------|------|------------------|
| RUNMYCAMPUS_CONSOLIDATED (Deferred and optional register) | 11.2 Tenant “Get blueprints”; 11.2 Pack versioning (tenant UI); 6.3/29.10 Tenant app billing (core now done — ledger on install; proration/invoice line optional) | 11.2: **Decide** — add tenant “Get blueprints” entry and/or version UI, or keep manager-only and document. 6.3/29.10: Optional proration/invoice from ledger when productised. |
| REMAINING_PHASES Phase 8 note | Rollback UI; legacy data cleaner; read-only legacy view; blueprint versioning UX; tenant-facing discovery; full tenant app billing | Rollback: Implemented (MigrationRun.rollback_*). Rest: **Decide** — schedule when migration/blueprint usage demands it. |
| phase8_migration_cloud_and_marketplaces.md | Rollback (later UI); legacy data cleaner; read-only legacy view; rollback-safe cutover/exception queue; tenant “Get blueprints”; versioning/compatibility (tenant-facing) | Same as above; document “done when” if you keep deferred. |
| WHY_WE_DEFERRED_AND_WHAT_WE_BUILT.md | Historical: scope approval, billing, policy caching — now implemented | Reference only. |
| CODE_REVIEW_GAPS_REDUNDANCIES.md | Merge/remove duplicate drag-and-drop JS | **Done:** Option B — customizer is settings-only; drag handled only by dashboard-layout.js. |
| REDUNDANCY_AND_PLAN_INDEX.md | “Only product/external Roadmap items remain deferred” | Align with REMAINING_PLAN_AUDIT_GAPS and REFINEMENT. |
| section_11_category_killers.md | Support co-pilot, guided onboarding, shadow sessions with masking, admin inactivity detection | **Decide:** Product roadmap or implement when prioritised. |
| offline_first_sync_16_5.md | Full offline UI (service worker, queue UI) — Partial / deferred | **Decide:** Schedule with offline/sync roadmap (REFINEMENT Priority 4). |
| government_district_intelligence.md | Full EMIS pipeline — Product roadmap / deferred | **Decide:** Keep as roadmap or assign year (e.g. Y4 in PLATFORM_ROADMAP_5Y). |

**Decision aid:** For each deferred item, either (a) **schedule** (sprint/year), (b) **implement now** if north-star aligned, or (c) **document** “deferred until [condition]” and owner.

---

### 2.4 “Roadmap” (planned for a year or “when we get to it”)

| Source | Item | What to do next |
|--------|------|------------------|
| PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md | §4 Prioritised backlog; §5 Execution order; §6 Year → focus (Y1–Y5) | Use for **planning**: pick items for current year/sprint from §4 and §6. |
| REFINEMENT Priority 3–4 | Ed-Fi, CEDS, WebAuthn; Student 360 UI, DynamicField, global ledger, offline, preview/canary, government, commercial | Map to roadmap years; pull into sprint when capacity allows. |
| section_15_scope_implemented_and_roadmap.md | 15.1–15.3 roadmap rows (full UI, transcript, DynamicField, payment plans, double-entry) | Already mapped; implement per roadmap year. |
| PLAN_COMPLETION_CHECKLIST.md | “Roadmap = not implemented; recorded for later” | Keep roadmap items in one place (this sweep or PLATFORM_ROADMAP_5Y). |
| PART_G_STANDARDS_STATUS.md | S3, S9, S12 (document only / roadmap) | No code required for checklist; keep doc as roadmap. |
| RUNMYCAMPUS_SINGLE_PLAN_COMPLETE / RUNMYCAMPUS_CODEBASE_AUDIT | Legacy import wizard, accreditation/evidence, PODs, marketing CMS, demo env, post-enrollment revenue, etc. — “add to roadmap” | **Decide:** Ensure each is in PLATFORM_ROADMAP_5Y or REFINEMENT or REMAINING_PLAN_AUDIT_GAPS so nothing is lost. |
| MARKETING_PUBLIC_SURFACE_BACKLOG.md | `later` queue: conversion funnel dashboards, copy variations, media optimization | **Decide:** Assign “later” to a year or leave as backlog. |

**Decision aid:** “Roadmap” = not lost. Ensure every roadmap item appears in **one** of: PLATFORM_ROADMAP_5Y, REFINEMENT, REMAINING_PLAN_AUDIT_GAPS, or this sweep. Then decide **target year or backlog** and owner.

---

### 2.5 “Partial” (partly done; remainder open)

| Source | Item | What to do next |
|--------|------|------------------|
| phase12_platform_configurability_section_10.md | Many rows “Partial” (e.g. required documents, term structure, GPA/rubric, fee templates, attendance, retention, density) | **Decide:** Per row, either close gap (policy/settings) or document remainder and leave as partial. |
| phase14_through_phase20 | 14.4, 14.5, 15.1, 15.2, 16.1, 16.3–16.6, 17.1–17.5, 18.1–18.3, 26.1–26.6 | See “Scoped” above; partial = part done, rest scoped. |
| phase21_through_phase24 | 29.1–29.10, 30.2–30.3 (Partial: …; … scoped) | Same. |
| blueprint_registry_current_state.md | Several “Partial” (grading/attendance presets, compliance/finance defaults, TenantPolicyPack, TenantFeatureEntitlement, etc.) | **Decide:** Implement missing registry/policy models or accept “in get_effective_policy / School” as sufficient and document. |
| FINDINGS_REPO_AUDIT.md | Full blueprint registry partial; workflow/dashboard hub as platform services; migration/marketplace “deferred to Phase 5–6” (now done) | Update FINDINGS: migration and marketplaces done; registry/hub status per blueprint_registry_current_state and phase4. |
| operational_identity_21_4.md | comms_defaults / fee_pack_defaults wiring Partial | **Decide:** Wire where needed or document as “keys in policy; modules consume”. |
| ux_rules_audit_26_5.md | Student onboarding: Partial (session/step state) | **Decide:** Add “Save draft” or document as acceptable partial. |
| runmycampus_gap_ledger.md | pending / partial placeholders; country/template branching; placeholder surfaces | **Decide:** Per row, implement or gate behind feature flag and document. |

**Decision aid:** For each “Partial”, either (a) **finish** the remaining slice, or (b) **document** the remainder and treat as “scoped” with next step and owner.

---

### 2.6 “Optional” (by decision not required)

| Source | Item | What to do next |
|--------|------|------------------|
| RUNMYCAMPUS_CONSOLIDATED (register) | 13.2 models.png — Optional by decision | No action unless you decide to add models.png. |
| phase8, phase6 | Tenant-facing “Get blueprints” — optional tenant backend entry later | **Decide:** Add for tenant UX or keep manager-only and document. |
| WHY_WE_DEFERRED | Policy caching — “Optional (add when scaling)” | No action until scaling demands it. |
| Many feature docs | Optional fields, optional enhancements, optional integrations | Use as product/backlog; no obligation to implement. |

**Decision aid:** “Optional” = no obligation. If you implement, update checklist; if not, leave as optional and document.

---

### 2.7 “Backlog” / “Prioritised backlog”

| Source | Item | What to do next |
|--------|------|------------------|
| PLATFORM_ROADMAP_5Y §4 | Prioritised backlog from REMAINING_PLAN_AUDIT_GAPS + REFINEMENT | **Decide:** Pull into Y1–Y2 sprints per table; update when done. |
| REFINEMENT_AND_IMPLEMENTATION_ORDER.md | Priority 1–4 tables | Use as **sprint backlog**; 1–2 items per sprint; update checklist when done. |
| INCOMPLETE_ITEMS_AND_NORTH_STAR_ALIGNMENT.md | “Implement now?” and immediate actions | **Decide:** Treat “Implement now? = Yes” as current backlog; close or reschedule. |
| MARKETING_PUBLIC_SURFACE_BACKLOG.md | `later` and prioritised items | **Decide:** Assign to roadmap year or leave as backlog. |

**Decision aid:** Backlog = work queue. Ensure every backlog item has **owner** and **target (sprint or year)** or is explicitly “no target” and why.

---

### 2.8 “Pending” / “Placeholder” / “Not yet”

| Source | Item | What to do next |
|--------|------|------------------|
| runmycampus_gap_ledger.md | pending: country/template branching; placeholder surfaces; partial PDF/BrandProfile | **Decide:** Replace with registries/policy or feature-flag placeholders; document. |
| WAVE_4_TASKS / seating chart | “Coming soon” placeholder | **Decide:** Implement or remove/gate; runmycampus_gap_ledger says seating-chart behind flag. |
| AUTOMATION_PLAN_FINAL / PAYROLL | PENDING status (approval queue) | Implementation detail; no doc decision. |
| TENANT_MEDIA_AND_DESIGN_STUDIO | Layout JSON placeholders; “full-screen canvas editor later” | **Decide:** Roadmap or implement when doing design studio. |

**Decision aid:** “Pending”/“Placeholder”/“Not yet” = either **implement**, **gate behind flag**, or **document** as roadmap and owner.

---

## 3. Single “what to do next” checklist

Use this to decide and track.

- [x] **Done when (open):** Parent mobile-first viewport done (portal_base.html); sandbox hardening CSP + sandbox attribute done (sandbox_embed). UX rules: ux_rules_audit_26_5.md; prioritise lists/forms per product.
- [x] **Scoped:** Addressed via IMPLEMENTATION_EXECUTION_PLAN — SoR/Experience doc (sor_vs_experience_17_1.md); rest documented with roadmap/REFINEMENT; pick 1–2 items per quarter from PLATFORM_ROADMAP_5Y §4.
- [x] **Deferred:** For each deferred item (11.2 tenant Get blueprints, pack versioning UX, migration legacy/read-only view, etc.), decide: schedule (sprint/year), implement now, or “deferred until [condition]” + owner.
- [x] **Roadmap:** Ensure every “add to roadmap” from RUNMYCAMPUS_SINGLE_PLAN, PART_G, etc. is in PLATFORM_ROADMAP_5Y or REFINEMENT or REMAINING_PLAN_AUDIT_GAPS.
- [x] **Partial:** For phase12 and blueprint_registry “Partial” rows, either close gap or document remainder + next step.
- [x] **Optional:** 13.2 models.png optional by decision; tenant Get blueprints implemented; no change unless product chooses.
- [x] **Backlog:** REFINEMENT and PLATFORM_ROADMAP_5Y §4 in use; execution plan ties to roadmap years.
- [x] **Placeholder/pending:** runmycampus_gap_ledger and placeholder decisions in IMPLEMENTATION_EXECUTION_PLAN §4 and §7; seating chart gated (enable_seating_chart_beta).

---

## 4. References

- **IMPLEMENTATION_EXECUTION_PLAN.md** — Execution status for all sweep categories (Scoped, Deferred, Roadmap, Partial, Optional, Backlog, Pending/Placeholder, Done-when). Use for “implement everything” progress.
- **DONE_WHEN_AND_SCOPED_WORK_LIST.md** — Phase “Done when” + scoped/deferred items with “reason not done”.
- **REMAINING_PHASES_EXECUTION_ORDER.md** — All 24 phases and “Done when” criteria.
- **REMAINING_PLAN_AUDIT_GAPS.md** — 6.3, 11.2, 1.8, 26.5, control plane.
- **REFINEMENT_AND_IMPLEMENTATION_ORDER.md** — Priority 1–4 partial/scoped items.
- **PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md** — 5-year horizon and prioritised backlog.
- **INCOMPLETE_ITEMS_AND_NORTH_STAR_ALIGNMENT.md** — “Implement now?” and immediate actions.
- **RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md** — Deferred and optional items register (§ after Part F).
