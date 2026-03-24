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

**Status tracking:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) — section **§0 → “ZIP execution plan — Phase 1”** (line-by-line tasks + acceptance). This matrix is the **implementation** reference.

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

- `apps/platform_runtime/tests/test_marketing_shell.py`: marketing base does not include app-only stylesheets.
- Add test: control_plane_skeleton does not include marketing-only stylesheets (tokens-marketing.css, marketing-shell.css).

## References

- `docs/MARKETING_SHELL_VIEWS.md`
- `templates/base.html`, `templates/portal_base.html`, `templates/control_plane_skeleton.html`, `templates/marketing/base_marketing.html`
