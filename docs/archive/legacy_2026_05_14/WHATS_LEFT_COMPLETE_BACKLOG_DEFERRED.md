# What’s Left: Complete, Backlog, Save for Later, Deferred

**Single reference** for what remains to complete, what’s in backlog, and what is explicitly deferred or “save for later.”  
**Source of truth for 9.5:** `docs/MASTER_PLATFORM_CHECKLIST.md`. This file is a **consolidated view** only.

---

## 1. Studio OS — Still to complete

From **`docs/Studio_OS_Remaining_Work_Non_Negotiable.md`**. All were non-negotiable; most are done. **Remaining:**

| # | Item | Status | Notes |
|---|------|--------|-------|
| 2.1 | **Shared preview engine** | Done | Single entry point `studio_os:preview`; experience delegates to preview_from_form; other modes return embed URL. |
| 2.2 | **Shared publish/rollback service** | Done | `studio_os:publish`, `save-draft`, `version-history`, `audit`; Experience persist via perform_theme_experience_publish. |
| 3.3 | **Experience left rail (in-mode)** | Done | Brand identity, Theme packs, Layout presets, Portal shells in Experience canvas (experience.html). |
| 3.4 | **Live preview in canvas** | Done | theme_colors_content includes theme_preview_assets + theme_preview_section; full live preview in Experience canvas. |
| 3.5 | **Experience right rail** | Done | Token properties, a11y (contrast), publish/rollback in right rail; theme_token_values + shell.html block. |
| 4.2–4.4 | **Launch left/right rail + refactor** | Done | launch_payload in-page (progress, health, steps, CTA); rails show role/confidence; guided onboarding data from setup_studio. |
| 5.2–5.4 | **Automation left/right rail + helpers** | Done | Workflow packs, trigger/action catalog; simulation summary, activation controls; “workflow list for school” helpers. |
| 6.2, 6.4 | **Output left rail + right rail** | Done | Output types, report/document packs, filters; style, branding, dependencies, publish in right rail. |
| 7.1–7.3 | **Control in-page (no iframe)** | Done | Feature control in-shell via control_panel_html (get_feature_control_panel_context + partial); left rail capabilities/audit; right rail impact/audit/rollback. |
| 9.3 | **Preview in same shell** | Done | Bottom bar Preview; theme form → preview_from_form. |
| 9.4 | **Publish/rollback in same shell** | Done | studio_rollback view; bottom bar Publish/Rollback. |
| 9.6 | **Recommendations in shell** | Done | Recommendations block in shell; next-best-action per mode in recommendations. |

**Summary:** Studio OS non-negotiable items are **done**. Control in-shell uses partial (no iframe); Experience/Launch/Control rails and live preview complete.

---

## 2. Backlog — Phase 10 (Path-to-10)

From **`docs/PHASE_10_BACKLOG.md`**. Not required for 9.5/10; tracked for **path to 10/10**.

| Area | Item | Status | Notes |
|------|------|--------|-------|
| **Siteconfig** | 1.2 State-safe migrations; 1.3 Delete legacy paths | Done | 1.2 Done: RuntimeDefaults, backfill, get_effective_site_settings overlay; emis uses runtime first. 1.3 Done: allowlist enforced; policies/resolver migrated. |
| **Architecture** | 2.1 Giant-file decomposition | Done | portal/schools/finance/api splits done; re-exports for URL wiring. |
| **Runtime** | 3.1 Governor limits enforcement | Done | API usage wired; other counters placeholder until instrumented. |
| **Event** | 4.1 Orchestration layer | Done | PHASE_10_BACKLOG: FeeFollowUpRunner, AdmissionsRunner, workbench, execute/compensate, SLA. |
| **Marketing** | 7.1 AI visuals | Done | get_marketing_ai_asset_url() in marketing_views; hero_dashboard_image_url, hero_video_url; MARKETING_AI_ASSET_KEYS. |
| **Developer platform** | 8.1 API portal, webhooks, SDKs | Done | API keys CRUD; APIQuota; webhook CRUD; TenantApiQuotaMiddleware; SDK/cert/sandbox stubs. |
| **Governance** | 9.1 Command rationalization | Done | Index; obsolete deprecated; expose ops in control-plane UI = future. |
| **Toolsets** | 10.1 ExperiencePack | Done | ExperiencePack packageable; Studio Experience theme_colors + publish/rollback; compare/rollback in studio_os. |
| **Toolsets** | 10.2 Feature Control registry | Done | Inspector shows FeatureToggleState (key, is_enabled, source, expires_at); get_feature_toggle_inspection(school). |
| **Toolsets** | 10.3 ReportPack | Done | ReportPack in reports; Studio Output Reports/Documents tabs; preview with sample data; dependency mapping. |
| **Toolsets** | 10.4–10.9 Document Library, Design Studio, Live Previews, Workflows, AI & API, Configuration Control Center | Done | 10.4 DocumentPack lifecycle/retention; 10.5–10.9 per PHASE_10_BACKLOG (layout, preview, simulation, AI audit, get_solo CI). |

**Summary:** Phase 10 path-to-10 aligned with PHASE_10_BACKLOG. Event 4.1, Marketing 7.1, Developer 8.1, Toolsets 10.1–10.9 at done/target level.

---

## 2.1 Product backlog — durable **staged drafts** + **fleet workflow** orchestration

**What it is (beyond what is already shipped):** A **cross-cutting data + state machine** for fleet changes: persisted **drafts/proposals**, optional **approval**, **scheduled apply**, **target scope** (school list / segment), and a **single auditable trail** that *coordinates* existing levers (staged activation, package rollout, feature control, Studio publish/rollback) instead of only linking to them. This is **not** the same as the Phase 3 **operator control model** (`build_operator_control_model_for_request`) — that path is **navigation + UX**; this backlog item is **orchestration + persistence**.

| Question | Answer |
|----------|--------|
| **Do we need it at all?** | **Not for current Phase 3 / 9.5 closure.** Many schools can run governed changes using **today’s surfaces** (staged activation, package rollout, Control rollback, diff/impact, feature audit, Studio publish). |
| **Why we might *not* do it** | **Cost and overlap risk:** large schema, UI surface area, idempotency, conflict rules, and tests. Without a **named pain** (see triggers below), it duplicates concepts the product already exposes and becomes a second “engine” to maintain. |
| **Why we *should* do it (triggers)** | **(1) Compliance / enterprise** — customers require **immutable fleet change records** and **approval chains** (SOC/ISO sales motion, district RFP). **(2) Scale / collisions** — many operators changing the same fleet scope and **overwrites or silent drift** in production. **(3) Revenue** — a signed deal is **blocked** on “staged fleet rollout with sign-off,” not on clearer links. |
| **If we build it** | **Thin vertical slice first:** one change type (e.g. one class of flag/pack), states `draft → pending_approval → scheduled → applying → succeeded|failed`, who/when/scope, **reuse existing apply paths** underneath, tests on transitions — then expand. |

**Status:** **Thin slice shipped (persistence + state machine + operator entry points).** `platform_runtime.FleetGovernedChange` with transitions in `apps/platform_runtime/fleet_governed_change.py`, migration `0008_fleetgovernedchange`, platform admin + `super:admin_bridge` (`fleet_governed_changes`) + **`super:fleet_governed_changes`** (read-first table), Configuration Control Center links, `fleet_governed_change_created` / `fleet_governed_change_transitioned` → `PlatformEventLog`, tests in `apps/platform_runtime/tests/test_fleet_governed_change.py`. **Full orchestration** (scheduled workers, conflict rules, deep apply integration) remains **expand-from-here** when triggers fire.

**Related (already in repo):** `studio_os:automation_staged_activation`, `super:package_rollout`, `studio_os:rollback`, `studio_os:control_impact`, `siteconfig:feature_control_audit`, `services.studio_publish` / `studio_publish_api` — see [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) ZIP Phase 3.

---

## 3. Save for later — completed or closed

Items previously deferred are now **implemented** or **closed** as below.

| Source | Item | Status |
|--------|------|--------|
| ROADMAP_AND_OPTIONAL_CLOSURE | Pack versioning tenant UI | **Done.** Admin “Update bundle” exists; BlueprintPack.get_schools_needing_update(); tenant can request update via support or admin. |
| ROADMAP_AND_OPTIONAL_CLOSURE | Policy caching | **Done.** POLICY_CACHE_TTL in resolver; cache.get/set in apps/policies/resolver.py. |
| ROADMAP_AND_OPTIONAL_CLOSURE | models.png, other optional fields | Closed optional; no action. |
| ROADMAP_AND_OPTIONAL_CLOSURE | TENANT_MEDIA / canvas editor | Closed; roadmap when doing design studio. |
| DASHBOARD_AND_ADMIN_MASTER_PLAN | Deeper theme merging | Closed; separate phase after B4. |
| DASHBOARD_AND_OPTIONAL | Success/error toasts, help tooltips, lazy-load | **Done (toasts).** static/css/toasts.css + static/js/toasts.js; window.runmycampusToast(msg, type). Tooltips/lazy-load optional. |
| MESSAGING_WHATSAPP | WhatsApp Business API | Closed optional; wa.me + flags sufficient. |
| PRODUCTION_READINESS_GAPS | Finance request per-user limit | Closed optional. |
| RUNMYCAMPUS_GAP_ANALYSIS | Predictive engine, at-risk dashboard, blockchain credentials | Closed; 2026 / predictive roadmap. |

**Summary:** Save-for-later items are implemented (pack versioning, policy cache, toasts) or closed with ref.

---

## 4. Closed / no open rows

- **REMAINING_WORK.md:** Every row is **Done** or **Closed (Phase 10 backlog)**. No open 9.5 rows.
- **MASTER_PLATFORM_CHECKLIST.md:** Phases 0–8 Done; nothing deferred for 9.5; Path-to-10 in Phase 10 backlog.

---

## 5. Quick reference

| If you want to… | Look here |
|-----------------|-----------|
| **Full inventory (everything left: backlog, deferred, optionals, path-to-11)** | **`docs/WHAT_IS_LEFT_MASTER.md`** — single non-negotiable scope list |
| **Complete Studio OS** | §1 above + `docs/Studio_OS_Remaining_Work_Non_Negotiable.md` |
| **Execute Path-to-10** | §2 above + `docs/PHASE_10_BACKLOG.md` |
| **Staged fleet workflow** | **§2.1** — thin slice in `FleetGovernedChange`; expand orchestration when triggers apply |
| **Review deferred/optional** | §3 above + `docs/architecture/ROADMAP_AND_OPTIONAL_CLOSURE.md` |
| **Verify 9.5 and gates** | `docs/MASTER_PLATFORM_CHECKLIST.md` |
| **ASAP / quick wins** | `docs/PLAN_REMAINING_AND_ASAP.md` (governor wiring, empty states, obsolete command already done) |

---

## 6. Logical order for next execution

1. **Ledger §14** — Done. §14 set to DONE (NON_NEGOTIABLE_BACKLOG fully closed).
2. **Quick wins (done):** Harmony 7.2–7.9 in engine + HARMONIES; GradingDeadline only in migrations; DETAILED_IMPLEMENTATION_PLAN §7 complete.
3. **Studio OS:** 2.1 shared preview engine, then 2.2 full studio_publish_service; then rails 3.3–7.3.
4. **Path-to-10:** PHASE_10_BACKLOG — siteconfig 1.2/1.3, decomposition 2.1, toolsets 10.1–10.4+.
5. **Other:** Admin sidebar audit; CODE_REVIEW TODOs; format_date/format_currency; get_solo allowlist; hardcoded colors → tokens.

---

**Bottom line**

- **Completed (no open 9.5 promise):** Studio OS (§1) — shared preview, publish/rollback, in-mode rails, Control in-page (no iframe), Experience left/right rail, Launch payload, Recommendations. Path-to-10 (§2) aligned with PHASE_10_BACKLOG; toolsets 10.1–10.9 at done/target level.
- **Backlog (path-to-10):** Phase 10 backlog (§2) — all items Done or at target; see PHASE_10_BACKLOG.md.
- **Backlog (§11.4 sequenced — non-negotiable):** §2.1 beyond the shipped thin slice (workers, collisions, deeper apply wiring) — queued per SOT §11.4 with tests + execution log; ship when the slice is scheduled, not as permanent deferral.
- **Save for later / deferred:** §3 only; no open deferred without closure. Doc-audit §2 items: Closed (Phase 10); see DOCS_COMPLETION_AUDIT.md.

**Final audit (completed):** No item remains deferred, backlog, or save-for-later without being either completed or explicitly closed with reference to WHATS_LEFT / PHASE_10_BACKLOG.
