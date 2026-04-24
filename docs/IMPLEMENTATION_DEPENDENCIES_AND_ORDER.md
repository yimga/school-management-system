# Implementation Dependencies and Order

**Purpose:** Single reference for **all dependencies** and **everything needed** to implement the remaining RUNMYCAMPUS plan items. Use this to resolve dependency/ordering, refactor many call sites, complete scope (Studios, §7), fix docs (§9), and data/content (§12).

**Coordination:** Multiple agents may work on the backlog. Before starting an item, check [docs_truth_ledger.md](docs_truth_ledger.md) and [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md) for recent completion so work is not duplicated. Prefer a different step/phase if the one you planned is already in progress or done.

**Source of truth:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).

---

## 0. Dependency audit (why some items are NOT DONE / BLOCKED)

**Use this section** when rerunning an audit to see where things stand and what blocks progress.

| Blocker | Why NOT DONE | Unlock / resolve |
|--------|---------------|-------------------|
| **Step 6 (legacy path deletion)** | BACKLOG §2d: further URL/view removal **BLOCKED on product confirmation**. Agreed scope (customizer redirect, workflow-hub/report-library redirects) DONE. | Product sign-off to remove or redirect next legacy URL; then delete route/view and document in SUBTRACTIVE_CLEANUP_RELEASE_NOTES. |
| **Reports app: makemigrations --check** | Django discovers models only from `reports.models`. BI models (ReportDefinition, ScheduledReport, AdHocReportDefinition, etc.) live in `reports.bi_models`. Importing `bi_models` from `reports.models` causes **circular import** (reports → bi_models → runtime_blueprints → siteconfig.models_tooling → siteconfig.models). So `makemigrations --check --dry-run` reports "pending" for reports; generating migrations would create a **destructive** migration (delete those tables). | **Option A:** Break the circular import (e.g. siteconfig.models avoid importing models_tooling at module load, or move FormDraft). **Option B:** Run `makemigrations --check` per-app in CI and skip `reports` until Option A. Do **not** commit a migration that deletes ReportDefinition/ScheduledReport/AdHocReportDefinition — code still uses them via `apps.reports.bi_models`. |
| **§2.4 broad except / structured logging** | Incremental; remaining broad excepts are in **skipped** paths (siteconfig/management/, migrations, tests). Linter allowlist already 0 for all in-scope files. | Optional: expand linter to include siteconfig/management and fix those files; or treat as complete for in-scope and document skip list. |
| **§8 marketing / full asset set** | MARKETING_FRONT_PLACEHOLDER: wiring DONE; remaining = **content/asset pipeline** (images, diagrams, copy), not application logic. | Create/source assets; plug URLs via env or static; no code blocker. |
| **Full Django test suite** | Large suite; DB creation and many tests take time. Phase H slice and targeted hardening tests run in pre_deploy_gate. | Run `python manage.py test --keepdb` in CI or nightly; fix failing tests per app. |

**Unlocked this run (2026-03):** (1) Fixed **IndentationError** in `apps/marketplace/tasks.py` (removed duplicate/orphan lines). (2) Fixed **SyntaxError** in `apps/people/people_management.py` (stray `}`). (3) Created **migrations** for platform_runtime (0005), schools (0035), siteconfig (0157) so `makemigrations --check` passes for those apps. (4) Reverted bad **reports** migration 0017 (would have deleted BI models still in use); documented reports blocker above.

---

## 1. Dependency / ordering

### 1.1 §2.1 SiteSettings / siteconfig — order of work

| Step | What | Depends on | Deliverable |
|------|------|------------|-------------|
| 1 | **Identify every tenant-facing read** | — | List from `site_settings_usage_inventory.md` + `lint_tenant_settings.py --report-allowlisted --base .` (allowlisted = migration backlog). |
| 2 | **Per field/usage:** Decide new source | Step 1 | For each: platform default only → RuntimeDefaults/helpers; brand → brand_experience; runtime/blueprint → resolver; policy → policies resolver; etc. (per domain_ownership). |
| 3 | **Implement or extend resolver/source** | Step 2 | e.g. add to `platform_runtime.helpers.get_effective_site_settings(request=, school=)` or bounded-context service that reads from RuntimeDefaults, blueprint, policy, etc. |
| 4 | **Migrate one call site** | Step 3 | Replace `SiteSettings.get_solo()` with `get_effective_site_settings(request)` or new service call; add tests. |
| 5 | **Repeat 4 for all call sites** | Step 3 | No new get_solo in tenant apps (CI); shrink allowlist in `scripts/lint_tenant_settings.py` ALLOWED_GET_SOLO_PREFIXES and SITESETTINGS_GET_SOLO_ALLOWLIST.md. |
| 6 | **Delete legacy path** | Step 5 for that path | Remove deprecated view/URL/re-export only after no callers remain; update SITECONFIG_OWNERSHIP_MIGRATION.md. |

**Current state:** Production get_solo is only in: `siteconfig/models.py`, `platform_runtime/helpers.py`, `siteconfig/management/`, `finance/management/`, `reports/management/`, `platform_runtime/management/commands/backfill_runtime_defaults.py`. All are control-plane or shim. Tenant apps are already blocked from new get_solo by CI. Remaining work: any tenant-facing code that still reads from SiteSettings via helpers (helpers.py is the intended shim) is correct; moving fields out of SiteSettings into bounded contexts is the next layer (schema/migrations + resolvers).

### 1.2 §11 Phase D — Retire old tool identities (after Studio modes)

| Step | What | Depends on | Deliverable |
|------|------|------------|-------------|
| 1 | **Implement each Studio mode** | §4.2–4.6 | Experience, Automation, Output, Launch, Control each have views/templates/APIs (see §2 below). **DONE.** |
| 2 | **Route legacy URLs to Studio** | Step 1 | **Agreed scope DONE:** admin/siteconfig/customizer/ → studio_os:experience (config/urls.py). Optional (per product): workflow hub → studio_os:automation; report library standalone → studio_os output; document in SUBTRACTIVE_CLEANUP_RELEASE_NOTES when done. |
| 3 | **Remove or deprecate legacy views** | Step 2 | Delete or 410 legacy view code only after product confirms; keep redirects until clients updated. |

---

## 2. Many call sites (refactor checklist)

### 2.1 get_solo → resolver (tenant-facing only)

- **Lint:** `scripts/lint_tenant_settings.py --check-get-solo-only` (fails on new get_solo in tenant apps).
- **Allowlist:** `scripts/lint_tenant_settings.py` ALLOWED_GET_SOLO_PREFIXES; doc: SITESETTINGS_GET_SOLO_ALLOWLIST.md.
- **Files to migrate (if any in tenant apps):** Run `python scripts/lint_tenant_settings.py --report-allowlisted --base .`; only allowlisted paths should appear (control-plane). Tenant-app code must not call get_solo; tests are excluded from lint.
- **Refactor pattern:** Replace `SiteSettings.get_solo()` with `get_effective_site_settings(request)` or `get_effective_site_settings(school=school)` where request is not available; use `platform_runtime.helpers` or bounded-context API.

### 2.2 Raw SQL → wrapper (per allowlisted file)

| File | Expected count | Action |
|------|----------------|--------|
| apps/schools/middleware.py | 0 | **Done.** Delegates to `schools.rls_context` (no inline `cursor.execute`). |
| apps/schools/onboarding_service.py | 1 | Wrap DROP SCHEMA (or tenant teardown) in a function in a repo/service module; call from onboarding_service. |
| apps/observability/db_liveness.py | 1 | **Done.** `check_db_liveness()`; `monitoring.check_database_health()` uses it. |
| apps/observability/views.py | 0 | **Done.** healthz + api_health use db_liveness.check_db_liveness(). |
| apps/schools/rls_context.py | 0 | **Done.** Session SQL in **`repositories/rls_context_repository.py`** (allowlisted); `rls_context` is API + guards only. |
| apps/siteconfig/cache_utils.py | 0 | **Done.** RLS GUC read in **`repositories/rls_session_repository.py`** (allowlisted); `cache_utils` delegates. |
| Other commands (ensure_tenant_schemas, db_health_check, etc.) | per allowlist | Keep or wrap in command-specific helper. |

**§2.4 allowlist manifest:** `scripts/allowlists/raw_sql_allowlist.json` lists **six** repository paths (see `docs/raw_sql_audit.md` §1). Session delegates (`rls_context`, `cache_utils`) are intentionally absent from the JSON.

**Refactor pattern:** (1) Add function in same app or repo that runs the SQL and returns result; (2) replace `cursor.execute` at call site with that function; (3) add test; (4) update raw_sql_audit.md and allowlist if count changes.

### 2.3 Signature/replay (per endpoint)

| Endpoint | Current | Action |
|----------|---------|--------|
| apps/billing/api_views.py (webhook) | Signature verified; 401 on invalid/missing | Done. Audit: BillingProcessorSyncEvent + upsert_webhook_incident. |
| apps/finance/views.py (payment_provider_webhook) | Signature verified; 401 on invalid/missing; WebhookLog for all attempts | Done. |
| apps/schools/section8_views.py (LTI) | manual_review_required | Add signature verification (e.g. LTI OAuth) and rate limiting per view. |
| apps/api/lead_capture_api.py | manual_review_required (audit) | Add rate limiting; optional signature if form post is signed. |
| config/graphql_view.py | manual_review_required | Rate limiting; audit logging for sensitive ops. |
| apps/accounts/views_saml.py | SAML; idp_assertion validity | Already has replay window. |
| apps/api/scim_views.py | Bearer token | Add timestamp/replay check and audit logging where missing. |

---

## 3. Scope — §4 Studios (modes) and §7

### 3.1 Experience Studio (§4.2)

**Depends on:** Shell (done). **Replaces:** customizer, theme colors, branding/theme pages, palette tool fragments, experience preview fragments.

| Need | Type | Where / how |
|------|------|-------------|
| ExperiencePack model | Model | e.g. `apps/brand_experience` or `packages`; fields: name, slug, theme_tokens, layout_ref, version, school_id, etc. |
| Theme tokens API | API | Resolve tokens from ExperiencePack or theme pack; used by portal shell and dashboard. |
| Portal shell layouts | Config/templates | Layout definitions; link to ExperiencePack or layout pack. |
| Dashboard visual packs | Model/API | Pack type for dashboard visuals; install/preview. |
| School website blocks | Model/API | Block library; link to experience. |
| Communication style packs | Model/API | Email/SMS templates and styles per pack. |
| Role/device preview | UI | Already in shell (studio_role_preview_entries); extend to Experience mode. |
| Compare / publish / rollback | API/UI | Reuse studio_preview, studio_publish_api, studio_rollback from shell. |
| Website brand import | Feature | Import flow (e.g. URL → fetch colors/logo); store in ExperiencePack or theme. |
| AI recommendations | Integration | Call studio_recommendations_api or setup_studio recommended_next. |

**Files to add/extend:** Views: e.g. `studio_os/views.py` (Experience mode); templates: `studio_os/experience_*.html` or mode-specific partials; URLs: `studio_os/urls.py`; models: new app or packages.

### 3.2 Automation Studio (§4.3)

**Replaces:** workflow hub, approval/workflow config fragments, workflow preview fragments.

| Need | Type | Where / how |
|------|------|-------------|
| Visual builder | UI | Workflow graph editor (front-end component or integrate existing). |
| Natural-language workflow generation | Feature | AI endpoint that returns workflow spec; wire to automation app. |
| Simulation engine | Service | Run workflow in dry-run; apps/automation or workflow engine. |
| Dependency graph | API/UI | Already in packages; extend for workflows. |
| Conflict detection | Service | Compare active vs staged workflow; report conflicts. |
| Staged activation | Feature | Apply workflow to staging then promote. |
| Replay / rollback | API | Reuse studio_rollback; workflow versioning. |
| Workflow health metrics | API/UI | Metrics per workflow run; observability or automation app. |

### 3.3 Output Studio (§4.4)

**Replaces:** report library, document library, design-studio output fragments.

| Need | Type | Where / how |
|------|------|-------------|
| ReportPack model | Model | e.g. reports app; versioned report definitions. |
| DocumentPack model | Model | e.g. portal or documents app; versioned document templates. |
| Sample-data preview | Feature | Preview report/document with sample data. |
| Branding inheritance | Logic | Resolve brand from school/theme; apply to output. |
| Signature requirements | Config | Per-document/report signature rules. |
| Retention/lifecycle controls | Config | Retention policy per pack type. |
| Dependency graph / publish / rollback | Same as shell | Reuse studio pattern. |

### 3.4 Launch Studio (§4.5) — partial today

**Already have:** setup_studio payload (health_summary, recommended_next, role_previews); studio shell role preview; recommendations API.

| Need | Type | Where / how |
|------|------|-------------|
| create school | Flow | Schools signup/create; wire to Launch mode. |
| select plan | UI | Plan picker; plans_entitlements. |
| recommend blueprint | API | Use setup_studio recommended_next or catalog. |
| import branding | Flow | Same as Experience website brand import. |
| starter stack / migration path | Flow | Setup_studio step definitions; migration cloud. |
| preview by role | Done | studio_role_preview_entries. |
| launch checklist | UI | List from setup_studio payload (steps, blockers). |
| setup health score | Done | health_summary in payload. |
| launch confidence summary | UI | From launch_ready + launch_blockers. |

### 3.5 Control Studio (§4.6)

**Replaces:** feature control panel, system config sprawl, runtime/blueprint/integration governance fragments.

| Need | Type | Where / how |
|------|------|-------------|
| Capability management | UI | Feature toggles; runtime inspector (done). |
| Runtime/source tracing | UI | get_runtime_inspection; "why enabled" (done). |
| Policy / entitlement / pack / integration governance | UI/API | Catalogs and super_* views; link from Control mode. |
| Registry overlays | UI | Global registries; overlay per school/region. |
| Metadata governance | Done | metadata_governance_ui. |
| Diff / impact summary / rollback | Reuse | studio_preview, _build_impact_summary, studio_rollback. |
| AI cleanup suggestions | Feature | Optional; suggest deprecated flags or unused config. |

### 3.6 §7 — Ecosystem seed and marketplace

| Need | Type | Where / how |
|------|------|-------------|
| Fill MARKETPLACE_SEED_TARGETS | Data | Run `python scripts/generate_platform_inventory.py --write`; copy counts into docs/MARKETPLACE_SEED_TARGETS.md; optionally script that reads platform_inventory.json and writes targets. |
| 25+ apps, 25+ blueprints, etc. | Data | Seed DB with app/blueprint/workflow/dashboard/policy pack records; use platform_inventory as source of truth for what exists. |
| Marketplace trust/install UX | Features | Listing pages; install flow; trust badges (reviews, verified publisher). |
| Package reports/documents/themes/setup flows | Pack types | ReportPack, DocumentPack, ExperiencePack (see above); setup flows as pack type. |

---

## 4. Documentation (§9)

| Task | Action |
|------|--------|
| MASTER_PLATFORM_CHECKLIST vs RUNMYCAMPUS | State at top: "9.5/10 is not claimed until RUNMYCAMPUS §12 gates are satisfied." Remove or rephrase any sentence that says "all phases 0–8 Done" or "9.5 bar complete" to align with §12 (siteconfig decomposed, runtime-only, Studio OS complete, etc.). |
| Policy | When editing any doc that mentions completion or 9.5, align with docs_truth_ledger.md and RUNMYCAMPUS §12. |

---

## 5. Data / content (§12 marketing)

| Task | Action |
|------|--------|
| Asset keys and wiring | Document in MARKETING_FRONT_PLACEHOLDER.md: for each required asset (hero, product, migration diagram, etc.), list context key, template path, and static path or CDN placeholder. |
| proof_hero_image_key | In use (marketing_landing hero data-proof-hero-key). |
| why_switch_bullets | In use; ensure template and context key documented. |
| Remaining assets | Create placeholder images or wire existing; each row in MARKETING_VISUAL_VERIFICATION.md gets "Verified in" path or "TBD — owner; target". |

---

## 6. Implementation order (recommended)

1. **§9 docs** — Align MASTER_PLATFORM_CHECKLIST and policy (no code).
2. **§2.4** — One raw SQL wrapper (e.g. observability/monitoring.py) and mark webhook audit done in public_endpoint_audit.
3. **§12 marketing** — Wire all placeholder keys and document asset list (templates + MARKETING_FRONT_PLACEHOLDER).
4. **§2.1** — Per site_settings_usage_inventory: implement one bounded-context source and migrate one call site (if any remain in tenant code); else document that only allowlisted control-plane paths remain.
5. **§4 Studios** — Implement one mode (e.g. Control Studio) using existing runtime inspector and metadata governance; then Experience or Launch next.
6. **§7** — Script to fill MARKETPLACE_SEED_TARGETS from platform_inventory; seed data for one pack type.
7. **§11 Phase D** — After at least one Studio mode is live, add one redirect from legacy URL to Studio.

---

**§9 alignment:** Completion authority is [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§0** + §12; **§12 engineering gate MET** (SOT §11.4). See [docs_truth_ledger.md](docs_truth_ledger.md).

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).*
