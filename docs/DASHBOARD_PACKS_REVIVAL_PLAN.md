# Dashboard Packs — Revival & Wiring Plan (handoff for a fresh session)

> ## ✅ EXECUTED — 2026-06-15 (SW v4.03.76)
>
> All phases shipped. **Phase 0 findings (grounded by direct read, agent claims moderated):**
> 1. **Seeder** (`seed_workflow_dashboard_packs.py`) created `DashboardPack` rows ONLY — **zero
>    `DashboardTemplate` rows** and empty `recommended_sectors`. Opt-in only (`RUN_BOOTSTRAP_PLATFORM_CATALOG=1`,
>    default off); never per-tenant. → Extended to create one default template per pack + per-pack sector
>    recommendations; now also force-seeded by data migration `0198` so packs exist in every environment.
> 2. **Resolver was PARTIALLY live, not fully dead** (an Explore agent over-claimed "LIVE" — moderated):
>    `portal_chrome.py` reads `TenantLayoutAssignment`/`DashboardPackAssignment` but ONLY for header/footer
>    **chrome**. The dashboard **content** (`role_home_engine` → `role_home_service` → `context.py`) read NONE
>    of them. → Phase 2 implemented: `dashboard_pack_resolver.overlay_role_home()` overlays the assigned
>    template's `config_schema["role_home"]` + `styling_overrides` onto the role-home default.
> 3. **Cockpit exists** (`dashboard_configuration_hub`, staff TenantLayoutAssignment editor) but was dead —
>    no templates to assign. Now populated.
> 4. **Provisioning seeded NO assignments.** → Phase B now calls `assign_default_dashboard_packs(school)`
>    (idempotent, non-fatal). Backfill: `manage.py assign_default_dashboard_packs [--apply]`.
>
> **What shipped:** `apps/siteconfig/dashboard_pack_catalog.py` (pure data), `dashboard_pack_resolver.py`
> (role-bucket map + sector cascade + assignment + render overlay + precedence chain), seeder + provisioning
> wiring + backfill cmd (Phase 1); `overlay_role_home` wired into `role_home_service` (Phase 2);
> `DashboardUserPreference.role_dashboard_packs` + migrations `0197`/`0198` + `DashboardPackPreferenceAPI`
> at `api:dashboard-pack-preference` (Phase 3); `components/dashboard_pack_switcher.html` +
> `static/js/dashboard-pack-switcher.js` + backend-dashboard CSS, SW bump (Phase 4).
> **Tests:** `apps/siteconfig/tests/test_dashboard_packs_revival.py` — 18 tests green. All zero-tolerance
> gates clean; `makemigrations --check` → "No changes detected"; single migration leaf (0198).
> Precedence: per-user choice → TenantLayoutAssignment → DashboardPackAssignment → role-home default
> (default always wins → never blank).

> ## ✅ PHASE 4b — switcher UX elevation (2026-07-09, SW v4.05.112)
>
> Owner feedback: the "Choose your dashboard" surface (`hero_greeting.html:35` → this
> switcher) rendered a **flat ~30-item wall of text** for an ADMIN (the ADMIN coarse
> bucket switches across 13 families) with no sense of what each pack looks like. Not
> broken — thin. Fixed WITHOUT amputating the breadth (a bursar/librarian/nurse are all
> `role=ADMIN`; narrowing would orphan their packs — the reachability test enforces this):
> 1. **Grouped by family, primary first.** New `dashboard_pack_resolver.grouped_available_packs_for_user(user, selected_code=)` returns family groups with the user's own family (or the family of their *current* selection) first as prominent cards; every other reachable family sits under a collapsed "other role" `<details>`. `dashboard_pack_switcher_context` now emits `groups` + `primary_family` alongside the (preserved) flat `available`.
> 2. **Honest, config-derived preview per pack.** `available_packs_for_role` items are enriched via new pure-catalog `dashboard_pack_catalog.pack_preview(code, family)` (+ `family_label`/`kpi_label`/`theme_label` SOT maps): real `kpis` / `focus_areas` / `theme` / `header_variant` drawn from the SAME `_merge_profile` that seeds `config_schema` — so a card shows what selecting the pack ACTUALLY changes, with **no fabricated screenshots**.
> 3. **Card UI + mini-layout schematic.** `components/dashboard_pack_switcher.html` rewritten to grouped cards + new `components/dashboard_pack_option.html` partial; a CSS-drawn schematic (`rmc-dpk-*` grammar in `rmc-class-grammar.css`, token-only) reflects kpi_count + header_variant + theme. Native radio stays visible + brand-accented (accessible, zero-JS selection); the selected pack's family is always the expanded primary group, so the current choice is never hidden in a collapsed section. `dashboard-pack-switcher.js` unchanged (same `name="dashboard_pack"` + Apply hooks).
> **Tests:** `test_dashboard_packs_revival.py` +8 (catalog labels + `pack_preview`, resolver enrichment + grouping primary-first + coverage, context `groups`, template render) — 39/39 green. Gates clean for the touched files (render-safety 0, undefined-css 0 new, off-token 0, theme-locked 0). No migration, no model change.

**Authored:** 2026-06-15 · **Status:** EXECUTED 2026-06-15 · **Owner question that triggered it:**
*"Our tenants were supposed to have world-class dashboards, and a dashboard pack where each
profile (admin / teacher / parent / …) gets a tailored look, and users within a group can switch
which dashboard they prefer. What happened to these dashboard packs?"*

## TL;DR

The feature was **largely modeled and partially wired, then stalled** — "catalog without cockpit."
The models that implement exactly the owner's vision already exist. The gap is (likely) that
nothing **seeds packs per new school**, the **live dashboard render bypasses the assignment models**,
and there is **no per-user switcher**. A fresh session should **verify the wiring first, then close
the three gaps** — do NOT build new parallel models.

> ⚠️ Before writing any code, run **Phase 0** below. The "current state" here is grounded in a
> read-only audit; the one thing NOT yet proven is whether the runtime resolver actually drives the
> rendered dashboard or is dead. Confirm, don't assume.

---

## Verified current state (read-only audit, 2026-06-15)

### The models that ARE the "dashboard packs" — `apps/siteconfig/models_dashboard.py`
- `DashboardPack` — *"Reusable dashboard pack (e.g. School Admin Executive, Teacher Command
  Center). Groups templates; assignable by role to a school."* (`code`, `name`, `family`,
  `version`, `recommended_sectors`).
- `DashboardPackAssignment` — assign a `DashboardPack` to a **school** for a **role**
  (`unique_together = [["school", "role"]]`).
- `DashboardTemplate` — the actual layout/widgets/theme (`config_schema` JSON), belongs to a pack.
- `TenantLayoutAssignment` — *"Runtime: resolve TenantLayoutAssignment(school, role) → template →
  layout + theme."* per-school, per-role (`unique_together = [["school", "role"]]`,
  `styling_overrides`). **This is the intended runtime resolution path.**
- `DashboardUserPreference` — per-user prefs; already has the **per-role JSON pattern** to copy:
  `role_visual_presets` + `get_visual_preset(role)` / `set_visual_preset(role, preset)`. This is the
  precedent for the per-user *pack* switcher. (Only one definition; `apps/runtime_blueprints/models.py`
  just re-exports it — not a duplicate.)

### The LIVE role-dashboard render — `apps/dashboard/role_home_engine.py`
- `ROLE_HOME_BY_ROLE` maps role → home key (`ADMIN→implementation`, `TEACHER→teacher`,
  `PARENT→parent`, `PRINCIPAL→principal`, …). `resolve_role_home(role_code, intent)` returns a
  **hard-coded** `ROLE_HOME_CONFIG` dict.
- Consumed via `apps/dashboard/services/role_home_service.py::build_role_home_context()` →
  `apps/dashboard/context.py` → `accounts/backend_dashboard.html`.
- **It does NOT read `TenantLayoutAssignment`, `DashboardPackAssignment`, `default_dashboard_slug`,
  or any per-user pack choice.** This is the core disconnect: even a correctly-assigned pack would
  not change what renders.

### Seeding & resolver references that EXIST (Phase 0 must confirm they're live)
- Seed command: `apps/siteconfig/management/commands/seed_workflow_dashboard_packs.py`.
- Resolver/usage references: `apps/siteconfig/views_dashboard_config.py`,
  `apps/platform_runtime/runtime_resolver.py`, `apps/siteconfig/portal_chrome.py`,
  `apps/siteconfig/signals.py`, `apps/siteconfig/owned_models_registry.py`,
  `apps/schools/super_views_catalog.py`.
- Dead field to ignore/retire: `schools.School.default_dashboard_slug` (exists, never set at
  provisioning, never read). Do NOT build on it — the `*Assignment` models supersede it.

### Catalog data already present
- `apps/dashboard/phase7_dashboard_templates.py` — `PHASE7_DASHBOARD_TEMPLATES` (60+ full-page
  dashboards), including a literal `schools/super_dashboard_packs.html`. Gated by
  `scripts/verify_phase7_dashboard_markers.py`.
- `apps/dashboard/phase8_declarations.py` — structured declarations per template.

---

## Phase 0 — Verify wiring BEFORE building (no code, ~30 min)

Answer these with grep + reading, write findings at top of this doc:
1. Does `seed_workflow_dashboard_packs.py` actually create `DashboardPack` + `DashboardTemplate`
   rows, and is it invoked anywhere automatic (predeploy, provisioning, migration data step)? Or is
   it manual-only / never run?
2. Does `apps/platform_runtime/runtime_resolver.py` (or `views_dashboard_config.py` /
   `portal_chrome.py`) resolve `TenantLayoutAssignment(school, role) → template` and feed it into a
   rendered dashboard? Trace it to a template context var actually used in a live `.html`. If it
   dead-ends, that confirms the disconnect.
3. Is there ANY admin/operator UI that creates `DashboardPackAssignment` / `TenantLayoutAssignment`
   (e.g. `super_dashboard_packs.html`, `views_dashboard_config.py`)? If yes, the assignment cockpit
   exists and only the **runtime read** + **provisioning seed** + **user switcher** are missing.
4. Does provisioning (`apps/schools/tasks.py` Phase B seeding) create any dashboard assignment for a
   new school? (Expected: no — that's why new schools feel blank.)

**Decision gate:** if (2) dead-ends, the plan stands as written. If (2) is actually live, shrink the
plan to just **provisioning seed + per-user switcher** (skip Phase 2).

---

## Phase 1 — Seed packs + assign per school/role at provisioning (1 small data path; no schema change)

- Ensure `seed_workflow_dashboard_packs.py` (or a new idempotent seeder) populates a **real** set of
  `DashboardPack` + `DashboardTemplate` rows for each role family (Admin / Teacher / Parent /
  Student / Finance / Leadership), sourced from `phase7`/`phase8` catalogs — not invented.
- In `apps/schools/tasks.py` Phase B (alongside academic-year/term/subject seeding), create the
  default `DashboardPackAssignment` + `TenantLayoutAssignment(school, role, template)` for the
  school's roles. **Idempotent** (`get_or_create` keyed on the `unique_together` (school, role)).
- Choose the default pack via the **config cascade**, not a literal — key off
  `school.primary_sector` / `education_system` (DashboardPack already has `recommended_sectors`).
  No hardcoded slug. (Respects CLAUDE.md no-hardcoding.)
- Backfill command for existing tenants: `manage.py assign_default_dashboard_packs [--apply]`,
  per-row atomic, idempotent (mirror the `promote_dyna_assignments.py` pattern).

## Phase 2 — Resolve assignments at render time (only if Phase 0 shows the resolver is dead)

- Extend `role_home_service.build_role_home_context()` (or `resolve_role_home`) to consult, in order:
  **per-user pack choice → `TenantLayoutAssignment(school, role)` → `DashboardPackAssignment` →
  current hard-coded `ROLE_HOME_CONFIG`** as the final fallback. Never render blank — the role
  default must always win if nothing is assigned.
- Keep the resolver pure/testable; overlay the assigned `template.config_schema` +
  `styling_overrides` onto the role-home structure rather than replacing it wholesale (lower blast
  radius, preserves existing CTAs/destinations).

## Phase 3 — Per-user switcher (the "users can change which dashboard they like" part) — 1 migration

- Add `role_dashboard_packs` JSONField to `DashboardUserPreference` (mirror `role_visual_presets`
  exactly), plus `get_dashboard_pack(role)` / `set_dashboard_pack(role, code)` with the same
  validate-against-allowed-and-fallback shape as `get_visual_preset`.
- Extend `apps/api/user_preferences_api.py` (`PortalPreferencesAPI` already does the get/patch
  allowlist pattern) with the dashboard-pack choice (gate the allowed pack codes to those assigned
  to the school for that role — a user can only pick among packs their school installed).
- Resolution precedence (Phase 2) already honors user choice first.

## Phase 4 — Switcher UI styled to the owner's designs

- Owner-provided design references (read these first):
  `C:/Users/yimga/OneDrive/Desktop/rmc-shell-preview-tenant-portal-v3-100x.html` and
  `rmc-shell-preview-v8-200x.html`.
- Surface a "Choose your dashboard" control in the dashboard shell (reuse the `.rmc-*` component
  grammar — segmented / sheet / cmdk — do NOT fork CSS; respect design-tokens). Preview-before-apply
  + save/resume to match the Setup-Studio interaction quality.

---

## Tests, gates, and governance (do not skip)

- **Seven-question declaration:** `role_home_engine.py` cites
  `docs/DECISION_ARCHITECTURE_CHECKLIST.md` + `docs/DASHBOARD_TAXONOMY_AND_REGISTRY.md` — any
  new/changed dashboard surface must add its registry row + declaration before merge.
- **Phase 7 markers:** if any full-page dashboard template is added, update
  `PHASE7_DASHBOARD_TEMPLATES` and pass `scripts/verify_phase7_dashboard_markers.py`.
- **No-hardcoding:** default pack selection routes through the cascade (sector/system), not literals;
  role strings reference `role_registry` / `User.Role` (scan_role_strings gate).
- **Tests:** provisioning seed idempotency (re-run creates no dup assignment); resolver precedence
  (user > tenant-assignment > pack-assignment > role default); switcher API rejects packs not
  assigned to the school; render never blank for a brand-new school.
- **SW bump** only if new JS/CSS ships (Phase 4).

## Gotchas (learned this session)

- **Peer churn:** the repo had 3 commits land *during* this audit (owner/Cursor working in
  parallel). Phase 3's migration is the collision risk — rebase/pull immediately before adding it,
  and keep the migration leaf isolated.
- **Test runner is flaky on this box:** in-memory build ~31 min; full-suite run this session errored
  on a `finance_webhooklog` unique-constraint test-isolation collision and was contaminated by a
  mid-run tree shift. Shard finance separately; treat a single combined run as advisory.
- **The first Explore audit missed `siteconfig/models_dashboard.py` entirely** (it only found
  `packages.InstalledPackage` + `role_home_engine`). Always confirm the `*Assignment` models are the
  real feature — they are.
- `schools.School.default_dashboard_slug` is a dead end; the `*Assignment` models supersede it.
  Consider retiring the field in a later cleanup (separate from this feature).

## Already fixed today (do NOT redo — just deploy)

The owner's screenshots (Access-required Setup_Studio wall, toast storm, onboarding redirect loop)
were all fixed in commits on 2026-06-15:
`9bcc5b4f7` (register setup_studio RBAC module), `38b5387e8` (dedup toasts by id),
`ab51a2379` (break new-owner onboarding redirect loop). They need a **prod redeploy**, not new code.
