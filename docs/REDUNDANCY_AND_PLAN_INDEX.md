# Consolidated plan index (single place to track)

**Purpose:** During this critical phase, track **only** the items in §1 below. All other plan/strategy/roadmap docs are superseded or reference-only; completion authority is RUNMYCAMPUS §12 and the four canonical docs. This file is the **only index** you need to avoid missing, overlooking, or duplicating work. **§6** is the single place to see how every external plan or directive (Cursor master prompt, Cursor implementation plan, 12 layers, UX directive, scroll-storytelling) maps into the SOT and where progress is tracked.

**Status lives in one place only:** **All "where we stand" and "what's left" status** is written and read in **[RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4** (and **§14** = same authority for historical links). Do not add status or "what's left" to PATH_TO_100, PLAN_AND_BACKLOG_STOCK_TAKE, phase batch docs, or this file. When reconciling, update SOT §11.4 first; then sync BACKLOG and (optionally) the stock take. The SOT **At a glance** table lists where to read each kind of status.

**How work is executed (not what to build):** every request — from a one-line fix to a platform-wide wave — runs the loop in **[RMC_STANDARD_EXECUTION_LOOP.md](RMC_STANDARD_EXECUTION_LOOP.md)**: **AUDIT (by running it, never by reading it) → IDENTIFY → FIX → TEST until green → RE-AUDIT from scratch → close residuals in the same pass → IMPROVE + seal → REPORT honestly.** That doc is a *principle*, not a plan: it carries no status and supersedes nothing in §1. It is mirrored as a non-negotiable directive in `CLAUDE.md`. Fixes resolve against the product thesis (the **AWS / Linux / Shopify / Salesforce of education**) with **local-first, global presence, and offline mode** as load-bearing pillars.

**For all agents:** Strategy and completion updates go **only** to the four canonical docs (§1). Do not create new strategy or roadmap files. When given a Cursor prompt, pasted implementation plan, or "12 layers" / UX / marketing directive, use **§6** to see where it lives and where to record progress; then update RUNMYCAMPUS, BACKLOG, docs_truth_ledger, or NEXT_50 as appropriate.

---

## 1. What to track (only these)

| # | Document | Role |
|---|----------|------|
| 1 | [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) | **Single execution source of truth** (streamlined: **At a glance**, §0–§14). §12 gates + §12.1 evidence; §11 execution order; **§11.4** = consolidated tracking. Detail: phase_checklists + enterprise audit. |
| 2 | [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) | **Backlog/closure.** Every unchecked/deferred item has status (DONE/PARTIAL/NOT DONE/BLOCKED) + closure note. §2e = next logical steps. |
| 3 | [docs_truth_ledger.md](docs_truth_ledger.md) | **Completion ledger.** Item → DONE / PARTIAL / NOT DONE. Snapshot of where we stand. |
| 4 | [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md) | **Numbered checklist.** Implementation order; status per step. |
| 5 | **This file** (REDUNDANCY_AND_PLAN_INDEX.md) | **Consolidated plan index.** One place to see what to track and what is superseded. |

**Deployment (no duplicate deployment plans):** [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for pre-deploy, migrations, launch. [RUNMYCAMPUS_DEPLOYMENT.md](RUNMYCAMPUS_DEPLOYMENT.md) if present — otherwise RELEASE_CHECKLIST only.

---

## 2. Implementation checklists (referenced by SOT; update when doing that work)

These are **not** sources of completion status. The SOT and BACKLOG reference them for specific work. Update them when implementing the referenced section only.

| Doc | Referenced by | Use |
|-----|----------------|-----|
| [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md) | RUNMYCAMPUS §10.5, Phase I | Edge-case, pack versioning, service/support, trust, dashboard taxonomy, content, design-system, boring excellence. |
| [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md) | RUNMYCAMPUS §8.0, BACKLOG §2e row 8 | One shell/sidebar/theme; marketing ultra high-end; implementation checklist. |
| [MASTER_PLATFORM_CHECKLIST.md](MASTER_PLATFORM_CHECKLIST.md) | BACKLOG §6, verification | Phase ledger; completion authority remains RUNMYCAMPUS §12 + docs_truth_ledger. |
| [RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md](RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md) | RUNMYCAMPUS (supporting doc) | Context and audit; execution checklist lives in RUNMYCAMPUS + BACKLOG. |

---

## 3. Superseded / reference-only (do not use as source of truth)

**Completion and “what to do next” come only from §1.** The docs below are **superseded** or **reference-only**. Do not update them for strategy or completion status; do not create new docs that duplicate them.

| Doc | Status | Authority instead |
|-----|--------|--------------------|
| RUNMYCAMPUS_SINGLE_PLAN_COMPLETE.md | Superseded | RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md |
| PLAN_COMPLETION_CHECKLIST.md | Superseded | BACKLOG + docs_truth_ledger + NEXT_50 |
| RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md | Closed; named plan only | RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md |
| THREE_PLANS_EXECUTION_GUIDE.md | Superseded | RUNMYCAMPUS + BACKLOG §2e |
| THREE_PLANS_MERGED_CHECKLIST.md | Superseded | BACKLOG §1 + §2e + NEXT_50 |
| MASTER_PLAN.md | Superseded | RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md |
| RUNMYCAMPUS_BLUEPRINT_FULL_EXECUTABLE_PLAN.md | Superseded | RUNMYCAMPUS + BACKLOG |
| PLAN_VERIFICATION_REPORT.md | Reference / verification only | Completion = RUNMYCAMPUS §12 + ledger |
| PLAN_COMPLETION_STATUS.md | Superseded | docs_truth_ledger + BACKLOG |
| RunMyCampus_Metadata_Driven_Gap_Closure_Plan.md | Reference / context | Execution = RUNMYCAMPUS + BACKLOG |
| RUNMYCAMPUS_AUDIT_PLAN_COMPLETE_NO_BACKLOG.md | Reference | RUNMYCAMPUS §12 + BACKLOG |
| All other docs matching *PLAN*.md, *plan*.md in docs/ | Superseded or domain-specific | For “is the plan complete?” and “what next?” use §1 only. Domain-specific (e.g. THEME_*, ADMIN_*, PAYMENT_*) are reference only; do not treat as execution plan. |

**.cursor/plans/*.plan.md:** Task-specific or historical. For execution source of truth and next steps use RUNMYCAMPUS and BACKLOG §2e; mark completed items in those plan files when the SOT says to sync.

---

## 4. Other gap/audit docs (scope only; not completion authority)

For “is the plan complete?” use RUNMYCAMPUS §12 and docs_truth_ledger. These cover specific scopes only:

| Doc | Purpose |
|-----|---------|
| CODE_REVIEW_GAPS_REDUNDANCIES.md | Structural/feature code review; TODOs. |
| GAPS_AND_REDUNDANCY_AUDIT.md | Templates, locale, placeholder TODOs. |
| GAPS_SECTION8_AND_TAGGING.md | Section 8 and tagging. |
| PREMIUM_FRONTEND_AUDIT.md | Premium frontend assessment; backlog/deferred. |
| REPORTS/AUDIT_LOG.md | Technical audit (tenant scope, i18n, audit trail). |

---

## 5. Redundancy rules (unchanged)

- **Single plan:** Only RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md is the execution source of truth.
- **Single completion set:** BACKLOG + docs_truth_ledger + NEXT_50. No duplicate closure/checklist docs.
- **Master Table List:** One doc (MASTER_TABLE_LIST.md).
- **Deployment:** RELEASE_CHECKLIST (and RUNMYCAMPUS_DEPLOYMENT if present); no extra deployment plan docs.

---

## 6. Consolidated plan and directive map (single place to track progress)

Use this section to see where every named plan, directive, or "12 layers" style checklist lives and how progress is tracked. **Do not create new docs for these;** they are already folded into the SOT and supporting checklists.

| Name / source | Where it lives in this repo | Progress tracked in |
|---------------|-----------------------------|---------------------|
| **12 operating-discipline layers** (edge-case, pack versioning, service/support, trust product, dashboard taxonomy, content/terminology, design-system behavior, boring excellence) | RUNMYCAMPUS §10.5; [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md) | RUNMYCAMPUS §11 Phase I; BACKLOG §2e row 13 |
| **Decision architecture** (seven questions: who, what question, what state, next action, confidence, wrong-path, fallback) | RUNMYCAMPUS §1.8; OPERATING_DISCIPLINE_LAYERS (meta-layer); [DECISION_ARCHITECTURE_CHECKLIST.md](DECISION_ARCHITECTURE_CHECKLIST.md) | §8.0 enforcement; DASHBOARD_TAXONOMY_AND_REGISTRY; DESIGN_SYSTEM_BEHAVIOR |
| **Cursor Master Prompt / North Star** (one shell, Studio OS, dashboard doctrine, security, marketplace, marketing, boring excellence) | RUNMYCAMPUS **§0–§11** + linked runbooks (SOT is the index; long narrative in enterprise audit + phase_checklists) | §11 Phases A–I; BACKLOG §2e; NEXT_50 |
| **Cursor Implementation Plan** (Phase 1 stop bleeding → … → Phase 9 boring excellence) | RUNMYCAMPUS §11 Phases A–I (same execution order) | §11; BACKLOG §2e; NEXT_50 |
| **UX ultra-high-end / dashboard directive** (one shell, one design system, dashboard doctrine, control-plane restructuring, 5-second rule, inverted pyramid, role-home) | RUNMYCAMPUS §8.0; [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md) | §8.0; BACKLOG §2e row 8 |
| **Scroll-storytelling marketing directive** (chapter narrative, pinned product frame, motion rules, marketing/product one family) | RUNMYCAMPUS §8 (marketing); [MARKETING_FRONT_PLACEHOLDER.md](MARKETING_FRONT_PLACEHOLDER.md); CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL | Phase F; BACKLOG |
| **RunMyCampus Enterprise Architecture Audit** | [RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md](RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md) (reference only) | Execution = RUNMYCAMPUS + BACKLOG; no separate checklist |

**How to use:** When you have a Cursor prompt, a pasted "Cursor implementation plan," or a "12 layers" / "UX directive" / "scroll-storytelling" checklist, **do not create a new plan file.** Check this table: the content is already represented in RUNMYCAMPUS and the implementation checklists (§2). Update only RUNMYCAMPUS, BACKLOG, docs_truth_ledger, or NEXT_50 for completion; update OPERATING_DISCIPLINE_LAYERS or CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL only when implementing that specific work.
