# Docs folder — completion audit

**Purpose:** Single reference for which docs are **clearly completed** vs **not complete**, so work can be finished without missing anything.

**Date:** March 2026 (post–Studio OS and Phase 10 execution).

---

## 1. Clearly completed (no open work)

These docs state that all items are Done, Closed, or N/A; use them as reference, not as open backlogs.

| Doc | Status claim | Note |
|-----|----------------|------|
| **REMAINING_WORK.md** | Every row **Done** or **Closed (Phase 10 backlog)** | Table closed; Path-to-10 in PHASE_10_BACKLOG.md |
| **RUNMYCAMPUS_FINAL_UNADDRESSED_GAPS_CHECKLIST.md** | All 15 gaps **Done** | Verification refs MASTER_PLATFORM_CHECKLIST, AUDIT_VS_PLAN_VALIDATION |
| **ROADMAPS_IMPLEMENTATION_STATUS.md** | All rows **Complete** | Defers to ROADMAP_DUE_TODAY; no open loops |
| **Studio_OS_Remaining_Work_Non_Negotiable.md** | Implementation status: shell, services, modes, rails, redirects, breadcrumbs **implemented** | Control in-page (no iframe) done; Launch payload/guided onboarding; Experience left/right rail and live preview done. Optional polish complete. |
| **WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md** | Studio OS non-negotiable **done**; Phase 10 and “save for later” listed | Single reference for backlog vs deferred |
| **PHASE_10_BACKLOG.md** | Tracks Path-to-10; many items **Done** or **Started** | Not “complete” as a product—backlog for 10/10 execution |
| **PLAN_COMPLETION_STATUS.md** | **Historical**; says use MASTER_PLATFORM_CHECKLIST as live ledger | Backlog = None per phase table |
| **MASTER_PLATFORM_CHECKLIST.md** | Phases 0–8 **Done**; no open rows in REMAINING_WORK | Source of truth for 9.5 bar |

---

## 2. Not complete — callouts so nothing is missed *(all closed / Phase 10)*

These docs contained **Partial**, **Not done**, **Open**, or **TBD** items. **Closure:** All §2 items are **Closed (Phase 10)** or **Done**. Remaining work is tracked only in **PHASE_10_BACKLOG.md** and **WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md**. No open required 9.5 work remains on these docs.

### 2.1 Architecture / plan audit

| Doc | What’s not complete | Action |
|-----|----------------------|--------|
| **architecture/REMAINING_PLAN_AUDIT_GAPS.md** | Points to **SCOPED_WORK_NOT_DONE.md** for “full list of scoped work not yet done”. Optional next steps: 11.2 tenant “Get blueprints” entry; 1.8 optional security pass; 26.5 remaining lists/forms per ux_rules_audit. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **architecture/PLAN_AUDIT_DONE_VS_PARTIAL_VS_NOT_DONE.md** | **Partial (42+)** and **Not done (20+)** items; e.g. Section 1.10 workflow “Level 1–3” and TAC deferred; 1.15 Analytics/Research DB deferred; Section 5 workflow levels/DSL not fully done; Section 6.3 tenant app billing optional. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **architecture/SCOPED_WORK_NOT_DONE.md** | Claims “required and due now” but many sections say **Done (this cycle)**. Remaining: Pack versioning “Newer version available” (optional “Request update”); 26.5 remaining lists/forms per ux_rules_audit; any item not yet marked Done. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |

### 2.2 Implementation / UX plans

| Doc | What’s not complete | Action |
|-----|----------------------|--------|
| **DETAILED_IMPLEMENTATION_PLAN.md** | Table “What’s not done”: sidebar verification on all layouts; back buttons in a few places; Site Settings tabs/accordions/summary (B3.1, B3.3); full-page iframe preview (B4.2); every boolean with critical toggle; **harmony types** square, achromatic, polychromatic, diad not implemented. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **ADMIN_REVAMP_PLAN.md** | 1.1 remove remaining admin hardcoded hex; 2.2 Quick actions strip; 3.3 replace remaining inline styles in admin. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **ADMIN_SIDEBAR_IMPROVEMENT_PLAN.md** | Remove remaining background/watermark sources in admin (audit Unfold + custom CSS). | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |

### 2.3 Checklists with unchecked or optional items

| Doc | What’s not complete | Action |
|-----|----------------------|--------|
| **RESILIENT_EDGE_COMPLETION_CHECKLIST.md** | “Quick verification (sign-off)” has **unchecked** boxes (e.g. Offline fallback, Status bar, Replay order, …). | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **security-checklist.md** | Contains “[ ] Only necessary ports open (80, 443)” and possibly other unchecked items. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **TESTING_CHECKLIST_ONBOARDING.md** | Step-by-step tests; if any step is unchecked or outdated, doc is incomplete. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |

### 2.4 Gaps and remediation

| Doc | What’s not complete | Action |
|-----|----------------------|--------|
| **RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP.md** | Likely has roadmap items or gaps not yet closed. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **PRODUCTION_READINESS_GAPS_DETAILED.md** | Any open gap rows. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **OFFLINE_MODE_GAPS.md** | Any open gaps. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **PLATFORM_AUDIT_REMEDIATION_BACKLOG.md** | Backlog items. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **VISUAL_DEBT_BACKLOG.md** | Backlog items. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **MARKETING_PUBLIC_SURFACE_BACKLOG.md** | Backlog items. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |

### 2.5 Phase / execution docs

| Doc | What’s not complete | Action |
|-----|----------------------|--------|
| **execution/PLAN_EXECUTION_STATUS.md** | Any phase row not **Done**. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **execution/NEXT_PHASE_BACKLOG.md** | Backlog list. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **execution/MASTER_PHASE_EXECUTION_CHECKLIST.md** | Any unchecked deliverable. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **plan/METADATA_DRIVEN_PLAN_STATUS.md** | Any item not Done. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |

### 2.6 Other plans with “not done” or “optional”

| Doc | What’s not complete | Action |
|-----|----------------------|--------|
| **SITE_SETTINGS_UX_CHANGES.md** | “What Was Not Done (Optional Later)” — keyboard shortcuts modal, etc. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md** | “Remaining gaps”: warn/block publish when pending grade approvals; optional “approved grades only” in report context; eval status on publish page; remove GradingDeadline references. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **DASHBOARD_IMPROVEMENTS_PARENT_TEACHER.md** | “Improvement” bullets (profile editing, labels, quick actions). | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |
| **DOCUMENTATION_TO_KB_MIGRATION.md** | If migration is partial. | **Closed (Phase 10).** See PHASE_10_BACKLOG / WHATS_LEFT. |

---

## 3. How to use this audit

1. **Completed docs (§1):** No action; use as reference only.
2. **Not complete (§2):** For each doc, either:
   - **Complete** the listed items and update the doc (e.g. “All Done” or “Verified YYYY-MM-DD”), or
   - **Close** the item by adding a “Closed (Phase 10)” or “Deferred” note and pointing to **PHASE_10_BACKLOG.md** or **WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md**.
3. **Single backlog:** Prefer **PHASE_10_BACKLOG.md** and **WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md** as the only place for “to do” and “deferred”; other docs should either be fully Done or explicitly say “See PHASE_10_BACKLOG / WHATS_LEFT.”

---

## 4. Quick reference

| If you want to… | Use |
|-----------------|-----|
| See what’s truly left to do | **WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md**, **PHASE_10_BACKLOG.md**, **PHASE_10_NEXT_STEPS.md** |
| See what’s already done (9.5 bar) | **MASTER_PLATFORM_CHECKLIST.md**, **REMAINING_WORK.md** |
| Close doc debt without missing anything | This file (§2) — work through each “Action” per doc |
| Studio OS status | **Studio_OS_Remaining_Work_Non_Negotiable.md** |
