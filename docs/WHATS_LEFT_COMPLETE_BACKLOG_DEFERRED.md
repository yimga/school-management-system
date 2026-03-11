# What’s Left: Complete, Backlog, Save for Later, Deferred

**Single reference** for what remains to complete, what’s in backlog, and what is explicitly deferred or “save for later.”  
**Source of truth for 9.5:** `docs/MASTER_PLATFORM_CHECKLIST.md`. This file is a **consolidated view** only.

---

## 1. Studio OS — Still to complete

From **`docs/Studio_OS_Remaining_Work_Non_Negotiable.md`**. All were non-negotiable; most are done. **Remaining:**

| # | Item | Status | Notes |
|---|------|--------|-------|
| 2.1 | **Shared preview engine** | Not done | One preview system for theme, workflows, outputs, launch, control. Reuse `site-settings-preview.js` / `preview_from_form`; extend to other modes. |
| 2.2 | **Shared publish/rollback service** | Stub only | Full `studio_publish_service`: save draft, validate, preview, publish, rollback, version history, audit. |
| 3.3 | **Experience left rail (in-mode)** | Not done | Inside Experience: Brand identity, Theme packs, Layout presets, Portal shells (beyond shell mode switcher). |
| 3.4 | **Live preview in canvas** | Partial | Experience partial has form + palette; full live preview in same page (preview assets + JS) in canvas. |
| 3.5 | **Experience right rail** | Partial | Token properties, accessibility warnings, publish/rollback controls in right rail (reuse theme_colors flow). |
| 4.2–4.4 | **Launch left/right rail + refactor** | Partial | Progress rail, role preview, launch confidence in rails; guided onboarding returns data/partial for Studio (no iframe). |
| 5.2–5.4 | **Automation left/right rail + helpers** | Partial | Workflow packs, trigger/action catalog; simulation summary, activation controls; “workflow list for school” helpers. |
| 6.2, 6.4 | **Output left rail + right rail** | Partial | Output types, report/document packs, filters; style, branding, dependencies, publish in right rail. |
| 7.1–7.3 | **Control in-page (no iframe)** | Not done | Feature control content in-shell; left rail (capabilities, policies, etc.); right rail (impact, audit, rollback). |
| 9.3 | **Preview in same shell** | Done | Bottom bar Preview; theme form → preview_from_form. |
| 9.4 | **Publish/rollback in same shell** | Done | studio_rollback view; bottom bar Publish/Rollback. |
| 9.6 | **Recommendations in shell** | Done | Recommendations block is implemented; optional: richer “next best action” per mode. |

**Summary:** Studio OS non-negotiable items are **done** (shared preview, publish/rollback service, in-mode rails, bottom bar Preview/Publish/Rollback, top bar search + Commands). Optional polish: Control form in-page without iframe; guided onboarding partial for Launch.

---

## 2. Backlog — Phase 10 (Path-to-10)

From **`docs/PHASE_10_BACKLOG.md`**. Not required for 9.5/10; tracked for **path to 10/10**.

| Area | Item | Status | Notes |
|------|------|--------|-------|
| **Siteconfig** | 1.2 State-safe migrations; 1.3 Delete legacy paths | Open | Migrations, backfill, switch reads to resolver; remove deprecated paths; CI. |
| **Architecture** | 2.1 Giant-file decomposition | Started | siteconfig AI → models_ai; split models.py, accounts/views, schools/super_views, portal/views, finance/views, api/views_v1; CI line thresholds. |
| **Runtime** | 3.1 Governor limits enforcement | Done | API usage wired; other counters placeholder until instrumented. |
| **Event** | 4.1 Orchestration layer | Started | apps/orchestration, ProcessDefinition, workbench at /super/orchestration/, seed_process_definitions. |
| **Marketing** | 7.1 AI visuals | Started | marketing_ai.py, get_marketing_ai_asset_url(); integrate into marketing. |
| **Developer platform** | 8.1 API portal, webhooks, SDKs | Started | API portal + webhook docs stubs at /api-center/. |
| **Governance** | 9.1 Command rationalization | Done | Index; obsolete deprecated; expose ops in control-plane UI = future. |
| **Toolsets** | 10.1 ExperiencePack | Started | ExperiencePack in packages. |
| **Toolsets** | 10.2 Feature Control registry | Open | Single capability registry with expiry; “why this feature is on” in inspector. |
| **Toolsets** | 10.3 ReportPack | Started | ReportPack in reports. |
| **Toolsets** | 10.4–10.9 Document Library, Design Studio, Live Previews, Workflows, AI & API, System Config | Open | Lifecycle, retention, packs; layout builder; central preview; simulation; contract tests; get_solo shrink. |

**Summary:** Phase 10 = path-to-10 and siteconfig migration. Several items **started**; rest are **backlog** for phased execution.

---

## 3. Save for later (explicitly deferred)

Items the codebase/docs mark as **optional**, **later**, or **deferred** (not required for 9.5; do when product/capacity allows).

| Source | Item | How it’s deferred |
|--------|------|-------------------|
| ROADMAP_AND_OPTIONAL_CLOSURE | Pack versioning tenant UI | Closed optional; update_bundle + admin exist; tenant “Update pack” UI optional. |
| ROADMAP_AND_OPTIONAL_CLOSURE | Policy caching | Add when scaling. |
| ROADMAP_AND_OPTIONAL_CLOSURE | models.png, other optional fields | Optional by decision; no action. |
| ROADMAP_AND_OPTIONAL_CLOSURE | TENANT_MEDIA / canvas editor | “Later”; roadmap when doing design studio. |
| DASHBOARD_AND_ADMIN_MASTER_PLAN | Deeper theme merging (ThemePacks inside Studio, unified color tool) | Separate phase after B4. |
| DASHBOARD_AND_OPTIONAL | Success/error toasts, help tooltips, lazy-load heavy widgets | Optional enhancements; pick for follow-up. |
| MESSAGING_WHATSAPP | WhatsApp Business API | Optional paid path; wa.me + flags sufficient for free. |
| PRODUCTION_READINESS_GAPS | Finance request per-user limit | Optional. |
| RUNMYCAMPUS_GAP_ANALYSIS | Predictive engine, at-risk dashboard, blockchain credentials | 2026 / predictive roadmap. |

**Summary:** “Save for later” = optional or scaling-driven; no open 9.5 promise. When to do: product/backlog or scaling need.

---

## 4. Closed / no open rows

- **REMAINING_WORK.md:** Every row is **Done** or **Closed (Phase 10 backlog)**. No open 9.5 rows.
- **MASTER_PLATFORM_CHECKLIST.md:** Phases 0–8 Done; nothing deferred for 9.5; Path-to-10 in Phase 10 backlog.

---

## 5. Quick reference

| If you want to… | Look here |
|-----------------|-----------|
| **Complete Studio OS** | §1 above + `docs/Studio_OS_Remaining_Work_Non_Negotiable.md` |
| **Execute Path-to-10** | §2 above + `docs/PHASE_10_BACKLOG.md` |
| **Review deferred/optional** | §3 above + `docs/architecture/ROADMAP_AND_OPTIONAL_CLOSURE.md` |
| **Verify 9.5 and gates** | `docs/MASTER_PLATFORM_CHECKLIST.md` |
| **ASAP / quick wins** | `docs/PLAN_REMAINING_AND_ASAP.md` (governor wiring, empty states, obsolete command already done) |

---

**Bottom line**

- **To complete (no “later”):** Studio OS shared preview, full publish/rollback service, in-mode rails and Control in-page (§1).
- **Backlog (path-to-10):** Phase 10 backlog (§2); implement in phases.
- **Save for later / deferred:** Optional and scaling items (§3); do when product or scaling demands.
