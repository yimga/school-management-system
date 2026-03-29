# Shell architecture matrix

**Purpose:** Four surfaces (marketing, control-plane, admin backoffice, tenant app) have one canonical base template and one asset bundle each. No mixing of shells.

## Matrix: surface → base template → assets

| Surface | Canonical base | Extends | Key CSS/JS | URL / context |
|---------|----------------|---------|------------|----------------|
| **Marketing** | `templates/marketing/base_marketing.html` | — | design-tokens, tokens-marketing.css, marketing-shell.css; Bootstrap. No design-system-unified, no dashboard-*. | Public product pages, runmycampus.com marketing. |
| **Control plane** | `templates/control_plane_base.html` | control_plane_skeleton.html | design-tokens, design-system-unified, **control-plane-primary-nav.css**, **control-plane-phase1-shell.css** (sticky action slot + context drawer), theme-visibility-guard, manager-control-plane.css, platform-high-end, surface-themes, table/form/card/chart, platform-responsive-touch. No marketing-shell. | `/super/*` (super dashboard, migration, tenant health, etc.). |
| **Admin backoffice** | Django admin / Unfold | config admin | Unfold/admin CSS; **manager host** also loads `control-plane-primary-nav.css`, `control-plane-phase1-shell.css`, shared **Context** drawer (`cp_context_drawer_shell.html`), **`vendor/bootstrap/js/bootstrap.bundle.min.js`** (Phase 1 — `data-bs` offcanvas/dropdown), Ctrl+K search + shortcuts (`admin/base_site.html`). Separate from tenant portal. | `/admin/` (manager or tenant admin depending on URL config). |
| **Tenant app** | `templates/base.html` (shared/login/errors) or `templates/portal_base.html` (portal/backend) | — | base.html: design-tokens, design-system-unified, dashboard-*, theme-*, platform-*. portal_base: design-tokens, design-system-unified, portal_theme, dashboard-*, etc. backend_base extends portal_base. | Tenant subdomain: login, dashboard, portal, backend. |

## Phase 1 — shell + navigation — **COMPLETE** (execution-plan Phase 1)

**Status tracking:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§0** — ZIP **Phase 1** (shell + navigation) is **COMPLETE**; verify commands point here + this matrix. Granular tasks: [phase_checklists/phase_01_authenticated_shell.md](phase_checklists/phase_01_authenticated_shell.md).

All Phase 1 acceptance items below are implemented in **code**; four surfaces still use four bases by architecture (see matrix above).

| Criterion | State |
|-----------|--------|
| Authenticated bases audited | **DONE** — matrix + `control_plane_base`, `admin` (Unfold), `portal_base` / `studio_os` shells. |
| Shared control-plane shell: top bar, left rail, breadcrumbs/page header row, main content | **DONE** — `control_plane_base.html` (`cp-navbar`, sidebar, `cp-page-header`, `cp_content`). |
| Sticky action bar (extensible) | **DONE** — `{% block cp_sticky_action_bar %}` (control plane); manager `/admin/`: `{% block admin_manager_sticky_actions %}` (`admin/base.html`); Studio preview/publish: `.cp-studio-sticky-actions` in `control-plane-phase1-shell.css`. |
| Contextual drawer / right rail | **DONE** — shared `partials/cp_context_drawer_shell.html` on control plane **and** manager `/admin/` (`base_site.html`); default body `control_plane_context_drawer_default.html`. |
| `/studio/control/`, Configuration Control Center (manager), `/super/*` on one spine | **DONE** — primary nav + manager CCC uses `console_domains_hub_control_plane.html` + shared outcome partial; Studio on manager uses `shell_control_plane.html` (no duplicate 8-pill inside canvas). |
| Primary nav: Home … Control | **DONE** — `build_primary_control_plane_nav` + `partials/control_plane_primary_nav.html`; manager `/admin/` includes same pills (`admin_nav_bridge.html`). |
| Command palette / global search | **DONE** — Ctrl+K + search field on control plane; Studio command palette (`shell_main_content.html` / `shell.html`). |
| No duplicate headers for primary spine | **DONE** — removed duplicate `PRIMARY_CONTROL_PLANE_NAV` from `shell_main_content.html` / `shell.html` when parent already has pills (`control_plane_base`). |
| Reduce `/super/` as only continuity story | **DONE** — sidebar “Recent” tracks `/super/`, `/studio/`, and `/admin/` (`control_plane_base.html` JS). |
| Sidebar role-aware | **DONE** — “Advanced Django admin” (`cp_platform_backoffice`) only if `request.user.is_superuser` (`control_plane_nav.py`). **Tests:** `test_control_plane_nav_roles.py`. |

**Phase 2** (design tokens on new UI): **DONE** for touched surfaces — `control-plane-primary-nav.css`, shared tokens in skeleton; not repeated here.

**Files (reference):** `apps/schools/control_plane_nav.py`, `apps/siteconfig/context_processors.py`, `templates/partials/control_plane_primary_nav.html`, `templates/partials/cp_context_drawer_shell.html`, `static/css/control-plane-primary-nav.css`, `static/css/control-plane-phase1-shell.css`, `templates/partials/control_plane_context_drawer_default.html`, `templates/control_plane_base.html`, `templates/control_plane_skeleton.html`, `templates/admin/base.html`, `templates/admin/base_site.html`, `templates/components/admin_nav_bridge.html`, `templates/studio_os/partials/shell_main_content.html`. **Tests:** `apps/schools/tests/test_primary_control_plane_nav.py`, `apps/schools/tests/test_control_plane_nav_roles.py`.

**Phases 3–11:** Authoritative status — **`docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`**, **`docs/BACKLOG_AND_DEFERRED_CLOSURE.md`**, **`scripts/pre_deploy_gate.sh`**. **Gate audit (what maps to what):** [PHASES_3_11_GATE_VERIFICATION.md](PHASES_3_11_GATE_VERIFICATION.md); **one-shot linters:** `python scripts/verify_phases_3_11_gates.py`.

## Hierarchy

- **Marketing:** `schools/marketing_base.html` → `marketing/base_marketing.html` (no further extend).
- **Control plane:** `control_plane_base.html` → `control_plane_skeleton.html` (skeleton has `<html>`, head, and body).
- **Tenant:** `backend_base.html` → `portal_base.html`. Standalone pages (login, errors, signup, find school) → `base.html`.
- **Admin:** Unfold/admin base_site.html.

## Rules

1. Marketing views must extend only `marketing/base_marketing.html` or `schools/marketing_base.html`; they must not load app-only CSS (design-system-unified, dashboard-*, theme-everywhere-dark).
2. Control-plane views must extend `control_plane_base.html` (or control_plane_skeleton); they must not load marketing-shell.css or tokens-marketing.css.
3. Tenant portal/backend views use portal_base or backend_base; shared/auth pages use base.html. No control-plane CSS in tenant views.
4. One base per surface; no cross-loading of surface-specific bundles.

## Tests

- `apps/platform_runtime/tests/test_marketing_shell.py`: marketing base does not include app-only stylesheets; `ControlPlaneShellTests` asserts control-plane skeleton does not load `marketing-shell.css` / `tokens-marketing.css`; **`StudioOsShellTests`** (batch 42 §11.4; re-run batch 51 §11.4 cadence) asserts `studio_os/shell.html` extends `portal_base.html` and `shell_extrastyle.html` does not pull control-plane or marketing shell CSS.
- `scripts/verify_shell_architecture_matrix.py`: static contracts for `templates/base.html`, **`templates/portal_base.html`**, and **`templates/studio_os/shell.html`** (+ `partials/shell_extrastyle.html`) (tenant/Studio spine; forbid cross-surface bundles). Wired into `verify_phases_3_11_gates.py` and `test_tenant_settings_lint.test_verify_shell_architecture_matrix_passes`.

## Staging URL manual pass (automation supplement)

Automated checks above do **not** replace loading each surface on a real host (marketing apex, manager control plane, tenant portal subdomain, tenant Django admin). Use this as a **per-release or pre-demo** checklist; fix duplicates or wrong bases one surface at a time.

| Step | Surface | What to verify |
|------|---------|----------------|
| 1 | Marketing | Open a public marketing URL; confirm **one** marketing bundle (no `design-system-unified` + dashboard stack mixed in). |
| 2 | Control plane | Open `/super/` (or manager equivalent); confirm **no** `marketing-shell.css` / `tokens-marketing.css` in network tab. |
| 3 | Tenant portal | Log into a tenant portal page extending `portal_base`; confirm `data-surface` / tenant shell CSS present; **no** control-plane primary nav CSS. |
| 4 | Studio | Open Studio shell; confirm it extends the tenant spine (`portal_base` hierarchy), not marketing or a second control-plane header stack. |
| 5 | Admin | Tenant vs manager `/admin/`: confirm Unfold shell; manager host should still align with control-plane nav bridge without duplicating tenant portal bundles. |
| 6 | Automation (local) | Before staging, run `python scripts/verify_shell_architecture_matrix.py` on your branch; fix any reported template/CSS contract violations **one template at a time** (same discipline as duplicate removal). |
| 7 | Duplicate bundles | In DevTools Network, watch for **double** loads of the same shell CSS or two competing headers on one page; trace to an extra `{% extends %}`, `{% include %}`, or duplicate block — remove one path per PR so reviews stay small. |

### Duplicate-bundle sweep (subtractive)

When step 7 fires, hunt **one** extra load path per PR:

- **`tokens-marketing.css` / `marketing-shell.css`** linked outside `marketing/` bases or marketing entry templates.
- **`control-plane-primary-nav.css` / `control-plane-phase1-shell.css`** on tenant `portal_base` / `base.html` / login chains (forbidden by architecture).
- **Second header stacks** — duplicate control-plane nav includes inside Studio canvas when the parent already provides the spine.

Re-run `python scripts/verify_shell_architecture_matrix.py` after each fix; keep [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md) seven-step table updated for **local** runs; use the sign-off log below for **live** hosts.

#### Repository audit log (append-only)

Template-level scans supplement automation; append a row after each **repo-wide** duplicate-bundle audit (no substitute for browser Network on live hosts).

| Date (UTC) | Scope | Finding | Command / notes |
|------------|-------|---------|-----------------|
| 2026-03-27 | `templates/**/*.html` | Repeat rg sweep: marketing bundle only in `templates/marketing/base_marketing.html`; control-plane shell CSS only in `templates/control_plane_skeleton.html` and `templates/admin/base_site.html` | `rg` (see marketing / control-plane static path greps); `python scripts/verify_shell_architecture_matrix.py` **PASS** |
| 2026-03-29 | `templates/**/*.html` | `tokens-marketing.css` / `marketing-shell.css` only in `templates/marketing/base_marketing.html`; `control-plane-primary-nav.css` / `control-plane-phase1-shell.css` only in `templates/control_plane_skeleton.html` and `templates/admin/base_site.html` | `python scripts/verify_shell_architecture_matrix.py` **PASS**; `rg` on those static paths under `templates/` |
| 2026-03-29 | `templates/studio_os/shell.html` + `partials/shell_extrastyle.html` | Extends `portal_base.html`; no cross-surface marketing or control-plane shell CSS in Studio root shell or extrastyle partial | `verify_shell_architecture_matrix.py` extended (batch 42 §11.4); `pytest apps/platform_runtime/tests/test_marketing_shell.py::StudioOsShellTests` |
| 2026-03-29 | Shell triad (full automation) | §11.4 batch 51 cadence: triad contracts unchanged (marketing / control-plane / admin / tenant base+portal+studio_os) | `verify_shell_architecture_matrix.py` **PASS**; `manage.py test apps.platform_runtime.tests.test_marketing_shell.StudioOsShellTests --keepdb` **2 OK** |

**Duplicate-bundle rows:** The **2026-03-27** and **2026-03-29** entries above both record the same marketing-vs-control-plane CSS placement invariant; both retained **append-only**. Prefer the **2026-03-29** row plus the Studio row for quick orientation.

## Staging / production URL matrix (reference)

Use **your** real staging/prod hostnames at release time. Examples below mirror ops docs—**not** a substitute for operator sign-off.

| Step | Surface | Example host (pattern) | Doc |
|------|---------|------------------------|-----|
| 1 | Marketing / public | `https://school-management-system-2kzk.onrender.com` (sample Render service URL) | [DEPLOY_RENDER.md](DEPLOY_RENDER.md) |
| 2 | Control plane | `https://manager.runmycampus.com/super/` | [RENDER_SHELL_AFTER_DEPLOY.md](RENDER_SHELL_AFTER_DEPLOY.md) |
| 3 | Tenant portal | `https://<school-slug>.runmycampus.com` | [RENDER_SHELL_AFTER_DEPLOY.md](RENDER_SHELL_AFTER_DEPLOY.md) |
| 3b | Tenant (Render subdomain style) | `https://<school-slug>.<service>.onrender.com` | [RENDER_SSL_AND_TENANT_URLS.md](RENDER_SSL_AND_TENANT_URLS.md) |
| 4 | Studio | `https://manager.runmycampus.com/studio/` | [RENDER_SHELL_AFTER_DEPLOY.md](RENDER_SHELL_AFTER_DEPLOY.md) |
| 5 | Admin | Manager or tenant host + `/admin/` | Matrix table above |
| 6–7 | Automation + duplicate bundles | Local `verify_shell_architecture_matrix.py`; repeat Network checks on **each** live host | [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md) hostname matrix |

**Local BR-13 evidence:** seven-step table + automation line in [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md).

### Operator sign-off log (staging / production)

Automation and localhost evidence **do not** close **P4** for real deploys. **Insert newest row directly below this line** (keep the template row at the bottom).

| Date (UTC) | Environment | Hosts tested (marketing / control plane / tenant / admin) | Steps 1–7 | Sign-off | Linked evidence |
|------------|-------------|------------------------------------------------|-----------|----------|-----------------|
| *— template: add real row above; keep this row last —* | *staging / prod* | *one URL per surface or “same as col 3 in URL matrix”* | *✓ or note gaps* | *initials* | *ticket / release note* |

**Evidence:** [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md) — **Shell architecture matrix — seven-step pass** (local `127.0.0.1`, **2026-03-28**) **and** **Staging / production hostname matrix**. This file adds **Staging / production URL matrix (reference)** plus **Repository audit log** for in-repo duplicate-bundle sweeps. **SOT:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) epic **P4** / Premium maturity **Shell triad** — re-verify on **your** live staging if a regression is suspected.

## References

- `docs/MARKETING_SHELL_VIEWS.md`
- `templates/base.html`, `templates/portal_base.html`, `templates/control_plane_skeleton.html`, `templates/marketing/base_marketing.html`
