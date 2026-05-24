# Preview Shell 100x Parity Plan — Three HTML North Stars

**Status:** **DONE (Lane 1, repo-scope)** — batches **1477–1483** complete; **PREVIEW_SHELL_100X_PARITY_COMPLETE** (execution batches **1477–1483**)
**Plan owner:** RunMyCampus platform UI/UX
**Created:** 2026-05-24
**Target SW range:** `sms-v3.84.0` → `sms-v3.90.x`
**Batch IDs:** **1477** (program) → **1478–1483** (implementation phases)
**Canonical previews (do not fork):**

| Slug | File | Surface |
|------|------|---------|
| `manager-v8-200x` | [`docs/generated/preview_app_shell_manager_v8_200x.html`](../generated/preview_app_shell_manager_v8_200x.html) | Control plane `/super/` |
| `admin-v1-200x` | [`docs/generated/preview_app_shell_admin_v1_200x.html`](../generated/preview_app_shell_admin_v1_200x.html) | Platform `/admin/` (manager host) |
| `tenant-portal-v3-100x` | [`docs/generated/preview_app_shell_tenant_portal_v3_100x.html`](../generated/preview_app_shell_tenant_portal_v3_100x.html) | Tenant portal (all roles) |

**Handoff-ready for:** Claude Code, Cursor, Codex — single build contract; do not spawn parallel UI strategy docs.

**Cross-links:**

- [`docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4 batches **1477–1483**
- [`docs/CSS_RETIREMENT_DOCKET.md`](../CSS_RETIREMENT_DOCKET.md) — record each wave
- [`docs/design/PAGE_AND_DASHBOARD_STANDARDS.md`](../design/PAGE_AND_DASHBOARD_STANDARDS.md)
- Mechanical gates: `scripts/verify_all_preview_shell_html_implementation.py`, `scripts/verify_platform_shell_preview_parity.py`, `scripts/verify_manager_admin_cp_layout.py`

---

## 0 — Executive summary

Three preview HTML files define **three non-interchangeable design languages**. Production must match each preview’s DOM order and visual grammar, then **exceed** it with motion, drill-down, and contextual intelligence — without breaking tenant brand cascade or multi-tenant isolation.

| Family | Mood | Header stack (top → bottom) | Grid |
|--------|------|-----------------------------|------|
| **v8 `/super/`** | Dark luxury cockpit | Utility → **live ticker** → `cp-primary-nav` | 3-col: sidebar + canvas + **copilot rail** |
| **admin v1 `/admin/`** | Dark backoffice catalog | Utility → **`cp-nav-row` pills** → **`cp-live-strip`** | 2-col: sidebar + canvas |
| **tenant v3** | Frosted glass, brand-forward | `tp-header__row` → **`tp-primary-nav`** | 2-col: sidebar + canvas |

**Program verdict at completion:** **PREVIEW SHELL 100X PARITY — REPO SCOPE** (live Render screenshot parity is Lane 2 operator evidence).

---

## 0.1 — Non-negotiable: AI copilot rail (DO NOT REFACTOR)

The **small right-column AI copilot rail** (`templates/partials/cockpit/_ai_copilot_rail.html`, `static/js/_pages/rmc-copilot-rail.js`, `static/js/rmc-copilot-rail.js`) is **out of scope for layout redesign**.

| Rule | Requirement |
|------|-------------|
| **Preserve** | Rail remains on manager `/super/` shell via `control_plane_skeleton.html` include; collapsed/expanded behavior unchanged |
| **Do not** | Move rail into canvas, remove grid column, or replace with floating FAB |
| **Page-aware help** | Keep `static/js/rmc-page-context-help.js` on all shells; ensure `active_url` + contextual `q` on every authenticated surface |
| **Contextual drawer** | Keep `help_contextual_drawer.html` fixed chip; separate from copilot rail |
| **Enhancement allowed** | Wire copilot suggestions from **current route metadata** (`data-rmc-page-personality`, breadcrumb, workflow key) — additive only |

Copilot rail verification every phase: `python scripts/verify_copilot_rail_contract.py` → **PASS**.

---

## 0.2 — What this plan rejects

1. One header stack for `/super/` and `/admin/` — previews differ by design.
2. Dark manager chrome on tenant hosts — tenant preview is light + `--school-*` tokens.
3. Stacking **two dashboards** on role home (cockpit v3 + legacy Bootstrap) — preview shows one canvas story.
4. Replacing Unfold admin with a full rewrite — skin + archetypes only.
5. Claiming “live beautiful” without Playwright + preview DOM-order gates green.

---

## 1 — Architecture rules (12)

1. **Preview DOM order is law** — enforced by `verify_platform_shell_preview_parity.py` + extended completion verifier.
2. **Semantic tokens only** — `design-tokens.css` + `.rmc-*`; no new hex forks in templates.
3. **`.rmc-app-shell` grid** — single scroll canvas; header/sidebar pinned per shell CSS.
4. **Copilot rail untouched** — see §0.1.
5. **Page archetypes** — every new/edited page extends `cp-operator-dashboard`, `cp-admin-backoffice`, or `tp-role-home` (introduced in Phase 4).
6. **4-fold cap** — long lists paginate; section nav when >2 folds.
7. **Empty / loading / error** — `cp-empty` (admin) + `tp-empty` (tenant) on every data surface.
8. **No operator data on tenant** — ticker namespaces already split; preserve.
9. **SOT discipline** — one §11.4 row per phase; autonomous log A–F **after** green gates only.
10. **SW monotonic bump** — each phase bumps `static/js/service-worker.js` `CACHE_VERSION`.
11. **22 zero-tolerance scanners** — stay at 0 after every phase.
12. **Tests prove behavior** — Django tests for new partials/services; Playwright for visual smoke in Phase 5.

---

## 2 — Phase map (mandatory order — 100% each before next)

| Batch | Phase | Goal | Primary proof |
|-------|-------|------|----------------|
| **1477** | Program | This plan + SOT + completion verifier scaffold | Plan + `verify_preview_shell_100x_program.py` PASS |
| **1478** | 0 — Contract freeze | Preview registry, page archetype stubs, gate bundle | `PREVIEW_SHELL_100X_PROGRAM_PASS` |
| **1479** | 1 — `/super/` v8 | Header order, sidebar grammar, landing canvas | `verify_platform_shell_preview_parity` + layout smoke |
| **1480** | 2 — `/admin/` v1 | Header order, index genome, changelist skin | `verify_admin_manager_shell_aggressive` + index markers |
| **1481** | 3 — Tenant v3 | Frosted header, hero, de-dupe role homes | `verify_tenant_portal_v3_100x_parity.py` (new) |
| **1482** | 4 — Inner pages | Archetypes, pagination, empty states | `verify_page_fold_standards` + `audit_page_standards` subset |
| **1483** | 5 — Surpass + certify | Motion layer, Playwright baselines, innovation | `verify_preview_shell_100x_completion.py` PASS |

**Lane 2 (operator):** Render screenshot diff vs preview HTML crops — not blocking repo-complete.

---

## 3 — Per-phase definition of done (100% — non-negotiable)

No phase is complete until **all** boxes pass. Fix gaps and re-run the full phase gate bundle before advancing.

### Universal gate bundle (every phase 1478–1483)

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python scripts/verify_copilot_rail_contract.py
python scripts/verify_interaction_integrity_completion.py
python scripts/scan_operator_shell_dead_hrefs.py --strict
python scripts/audit_template_render_safety.py
python scripts/verify_all_preview_shell_html_implementation.py
```

### Phase-specific gates (see §4)

After implementation: fix bugs → re-run phase gates → `verify_doc_plan_density_discipline.py` (end of program only) → SOT row **DONE** + autonomous log A–F.

---

## 4 — Phase specifications

### Phase 0 — Contract freeze (batch **1478**)

**Ship:**

- `scripts/verify_preview_shell_100x_program.py` — asserts three preview files exist + `IMPLEMENTATION` map in `verify_all_preview_shell_html_implementation.py`
- `scripts/verify_preview_shell_100x_completion.py` — program-level checklist (stub checks expanded each phase)
- `templates/archetypes/` stubs: `cp_operator_dashboard.html`, `cp_admin_backoffice.html`, `tp_role_home.html` (extends correct shells)
- `docs/generated/preview_shell_100x_parity_registry.json` (route → archetype → preview family)

**Gate:** `python scripts/verify_preview_shell_100x_program.py` → **PREVIEW_SHELL_100X_PROGRAM_PASS**

---

### Phase 1 — Manager v8 `/super/` (batch **1479**)

**Align to:** `preview_app_shell_manager_v8_200x.html`

**Ship:**

1. **Header DOM order:** utility → `cp-live-strip` (ticker inside) → `cp-primary-nav` in `control_plane_base.html` + manager `portal_base` bridge (already partially done — verify).
2. **Sidebar:** migrate toward `cp-sidebar__group` + pins (data from `CONTROL_PLANE_NAV`); keep `control_plane_sidebar.html` URLs.
3. **Landing:** `super_dashboard.html` — pulse + 200x sections only on landing; breadcrumb + `cp-page-h1-row` on all `control_plane_base` children via shared partial.
4. **Presence + tagline** in utility row (already in `manager_operator_topbar.html`).

**Do not touch:** `_ai_copilot_rail.html`, copilot grid column width defaults.

**Gates:**

```bash
python scripts/verify_platform_shell_preview_parity.py
python scripts/verify_manager_admin_cp_layout.py --css-only
python manage.py test apps.siteconfig.tests.test_manager_portal_chrome_contract
```

**DOM order proof:** rendered `/super/` HTML contains `cp-live-strip` before `cp-nav-row` / `cp-primary-nav`.

---

### Phase 2 — Admin v1 `/admin/` (batch **1480**)

**Align to:** `preview_app_shell_admin_v1_200x.html`

**Ship:**

1. **Header:** utility → `cp-nav-row` → `cp-live-strip` (confirm `admin/base.html`).
2. **Index:** keep `index_superadmin.html` as genome (`cp-hero`, `cp-steering`, `cp-kpi-strip`, `cp-catalog-card`).
3. **Changelist / change form:** extend `admin-200x-shell-overlay.css` + `admin/includes/*` for `cp-changelist`, `cp-form-frame`, `cp-empty`.
4. **Sidebar:** `manager_platform_admin_sidebar.html` — group labels + counts like preview.

**Gates:**

```bash
python scripts/verify_platform_shell_preview_parity.py
python scripts/verify_manager_admin_cp_layout.py
python scripts/verify_admin_manager_shell_aggressive.py --css-only
```

---

### Phase 3 — Tenant v3 100x (batch **1481**)

**Align to:** `preview_app_shell_tenant_portal_v3_100x.html`

**Ship:**

1. **Replace tenant header** in `portal_base.html`: real `tp-header__row` (brand, search, quick actions) + `tp-primary-nav`; **remove** legacy `navbar-dark topbar` from tenant branch (manager bridge keeps `cp-header`).
2. **`partials/tenant/hero_greeting.html`** — time-aware eyebrow, h1, child switcher hook, hero CTAs from portal quick actions.
3. **Role homes** (`parent/dashboard.html`, `teacher/dashboard.html`, `accounts/backend_dashboard.html`): **gate** legacy dashboard behind `{% if not cockpit.v3_home.enabled %}` OR remove duplicate column when cockpit partials render.
4. **Wire cockpit partials** already in tree: `_today_snapshot`, `_quick_actions_grid`, `_year_progress`, etc. — enable sensible SiteSettings defaults for demo school.
5. **Load** `rmc-tenant-dashboard-v2.css` + `rmc-tenant-header-100x.css` on tenant landings only.

**Gates:**

```bash
python scripts/verify_preview_shell_100x_tenant_parity.py   # new — see Phase 0 scaffold
python scripts/verify_page_fold_standards.py  # parent/teacher landings
python manage.py test apps.portal.tests.test_tenant_dashboard_v3  # add if missing
```

---

### Phase 4 — Inner pages & archetypes (batch **1482**)

**Ship:**

1. Migrate top 30 unpaginated operator lists from `docs/generated/template_scroll_compression_audit.json` priority list.
2. Apply archetype extends to list/form/wizard templates per route family in registry JSON.
3. **`cp-empty` / `tp-empty`** partials + include on all major list views.
4. **`data-rmc-scroll-policy="paginate"`** on tables.

**Gates:**

```bash
python scripts/verify_page_fold_standards.py
python scripts/audit_page_standards.py --json docs/generated/page_standards_audit.json
python scripts/audit_luxury_ui_surface.py
```

---

### Phase 5 — Surpass previews + visual certification (batch **1483**)

**Ship (innovation — token-safe):**

1. Pulse cards / snap cards click → bottom sheet drill-down (no new routes required).
2. Tenant hero: optional one-line contextual summary (rules tier, PII-safe).
3. Reduced-motion respect on ticker + hover micro-lift on quick tiles.
4. Playwright: `tests/e2e/preview-shell-parity.spec.js` — header crop + no horizontal overflow at 390/768/1366.

**Gates:**

```bash
python scripts/verify_preview_shell_100x_completion.py
python scripts/audit_luxury_ui_surface.py
npm run test:e2e -- tests/e2e/preview-shell-parity.spec.js   # when Django up
```

**Program gate:** `verify_preview_shell_100x_completion.py` → **PREVIEW_SHELL_100X_PARITY_COMPLETE**

---

## 5 — Aggressive build-agent prompt (copy-paste for autonomous runs — DO NOT REFACTOR copilot rail)

Use this verbatim when launching an agent on **one batch only**. Do not start batch N+1 until batch N is **DONE** in SOT with green gates.

```
You are implementing RunMyCampus Preview Shell 100x Parity — batch <BATCH_ID> only.

CANONICAL PLAN: docs/plans/PREVIEW_SHELL_100X_PARITY_PLAN.md
SOT: docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §11.4 batch <BATCH_ID>

NORTH STAR HTML (read-only reference, match DOM order not inline CSS):
- docs/generated/preview_app_shell_manager_v8_200x.html  → /super/
- docs/generated/preview_app_shell_admin_v1_200x.html   → /admin/
- docs/generated/preview_app_shell_tenant_portal_v3_100x.html → tenant portal

NON-NEGOTIABLE — AI COPILOT RAIL:
- DO NOT refactor, relocate, or remove templates/partials/cockpit/_ai_copilot_rail.html
- DO NOT change .rmc-app-shell grid copilot column contract in rmc-app-shell.css
- MAY enhance page-aware context passed to AI Center (rmc-page-context-help.js) additively only
- After every change: python scripts/verify_copilot_rail_contract.py must PASS

NON-NEGOTIABLE — EXECUTION DISCIPLINE:
1. Read the phase section in PREVIEW_SHELL_100X_PARITY_PLAN.md for batch <BATCH_ID> only.
2. Implement smallest production-ready diff; match existing repo patterns.
3. Run the phase "Gates" block from the plan — ALL commands must pass.
4. If any gate fails: fix root cause, re-run FULL phase gate bundle (not just the failing script).
5. Run Django tests you add or touch.
6. Bump static/js/service-worker.js CACHE_VERSION with slug preview-shell-100x-<phase>-YYYY-MM-DD.
7. Append docs/CSS_RETIREMENT_DOCKET.md wave note.
8. Update docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §11.4 batch <BATCH_ID> → DONE (Lane 1) with proof strings.
9. Update docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md A–F for this batch only.
10. STOP. Do not start the next batch. Report: files changed, gate outputs, honest residuals.

BANNED:
- New parallel strategy markdown outside the canonical plan
- Claiming phase complete without green named verifiers
- Touching copilot rail layout/CSS removal
- Hardcoded hex in templates
- href="#" without allow marker

Current batch scope: <PASTE PHASE TITLE AND SHIP LIST FROM §4>
Phase gates: <PASTE GATE COMMANDS FROM §4>
```

---

## 6 — Route → preview family registry (starter)

| Route family | Preview | Archetype | Landing template |
|--------------|---------|-----------|------------------|
| `/super/`, `/super/*` | v8 | `cp-operator-dashboard` | `schools/super_dashboard.html` |
| `/admin/`, `/admin/*` | admin v1 | `cp-admin-backoffice` | `admin/index_superadmin.html` |
| Parent home | tenant v3 | `tp-role-home` | `parent/dashboard.html` |
| Teacher home | tenant v3 | `tp-role-home` | `teacher/dashboard.html` |
| Backend admin home | tenant v3 | `tp-role-home` | `accounts/backend_dashboard.html` |
| Studio OS | v8 chrome only | `cp-console` | `studio_os/shell.html` |

Expand registry in Phase 0 JSON artifact.

---

## 7 — Innovation backlog (Phase 5+ only)

Tracked in SOT only after Phase 4 green — do not block parity:

- Focus mode (collapse sidebar + copilot to icons only — **copilot column stays**)
- Catalog Spotlight search on `/admin/`
- Tenant child-lens switcher with animated transition
- Achievement delight (reduced motion off)
- `/super/` pulse → incident drill-down sheet

---

## 8 — Honest residuals (Lane 2)

- Render deploy may lag local HEAD — `verify_manager_render_parity.py` when releasing
- Playwright full matrix needs `E2E_LOGIN_USER` + live server
- Some inner `/super/*` pages may remain `cp-console` archetype until Phase 4 burndown completes

**Repo-complete verdict:** **PREVIEW SHELL 100X PARITY — REPO SCOPE** after batch **1483** gates pass.
