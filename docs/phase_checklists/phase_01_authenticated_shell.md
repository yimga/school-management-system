# Phase 1 — Authenticated shell unification — checklist

**SOT:** ZIP Phase 1 — COMPLETE (this checklist captures verification + 2026-03-24 delta).

## Base templates / skeleton

- [x] `templates/control_plane_base.html` — manager control plane shell (navbar, pills, sidebar, `cp_content`)
- [x] `templates/control_plane_skeleton.html` — parent skeleton
- [x] `templates/portal_base.html` — tenant portal (**2026-04-25, batch 968:** inline dashboard-page script treats **`/studio/`** as **`page=studio`** for body **`data-dashboard-page`** / **`dashboard-page-studio`** class)
- [x] `templates/base.html` — tenant root
- [x] `templates/admin/base_site.html` — manager Unfold + bridge (per matrix)
- [x] `templates/studio_os/shell.html` — tenant Studio → `portal_base`
- [x] `templates/studio_os/shell_control_plane.html` — manager Studio → `control_plane_base`
- [x] `templates/partials/control_plane_primary_nav.html`
- [x] `templates/partials/control_plane_sidebar.html`
- [x] `templates/partials/cp_context_drawer_shell.html`

## Python / routes (representative)

- [x] `apps/schools/control_plane_nav.py` — primary nav + sidebar registry
- [x] `config/manager_urls.py` — `studio/`, `super/`
- [x] `apps/schools/super_urls.py` — super routes namespace
- [x] `apps/studio_os/urls.py` — Studio routes

## `/super/*` templates — `control_plane_base` compliance

Audit: every `templates/schools/super*.html` must extend `control_plane_base.html` **or** documented exception.

- [x] All super templates except legacy AI trio — already `control_plane_base`
- [x] `templates/schools/super_ai_model_hub.html` — migrated 2026-03-24
- [x] `templates/schools/super_global_ai_version.html` — migrated 2026-03-24
- [x] `templates/schools/super_global_ai_version_progress.html` — migrated 2026-03-24

## Views / context

- [x] `apps/schools/super_views_ai.py` — supplies `dashboard_url` (no change required post-migration)

## Studio OS deep-linked subpages (`/studio/experience/*`, `/studio/automation/*`, …)

- [x] `apps/studio_os/views.py` — `_render_studio_subpage`, `_studio_subpage_context`, embed vs full shell
- [x] `templates/studio_os/shell_subpage_wrap.html` — tenant: extends `shell.html`, overrides `studio_canvas`
- [x] `templates/studio_os/studio_subpage_embed.html` — `?embed=1` → `portal_base`
- [x] `templates/studio_os/partials/shell_main_content.html` — `studio_native_canvas_partial` first branch (manager)
- [x] `templates/studio_os/partials/subpages/*.html` — 23 canvas bodies (former portal-only pages)
- [x] Removed obsolete root `templates/studio_os/*.html` duplicates (same names as subpages)

## Validation

- [x] `python -m pytest apps/schools/tests/test_primary_control_plane_nav.py` — PASS
- [x] `python -m pytest apps/schools/tests/test_control_plane_nav_roles.py` — PASS
- [x] `python -m pytest apps/schools/tests/test_super_views_ai.py` — PASS
- [x] `python -m pytest apps/studio_os/tests/` — PASS
- [x] Grep: no `extends "admin/base_site.html"` under `templates/schools/super*.html`

## Granular checklist (maps to user spec)

- [x] Breadcrumbs — super: `{% block breadcrumbs %}` + `dashboard_url`; portal: `components/breadcrumb.html` / page-local nav where used
- [x] Nav helpers — `apps/schools/control_plane_nav.py` (`PRIMARY_CONTROL_PLANE_NAV`, sidebar registry)
- [x] Legacy super shell — no `super*.html` extends `admin/base_site.html` (grep); all extend `control_plane_base.html`
- [x] Full audit table — [PHASE_01_02_GRANULAR_AUDIT.md](../phase_audit/PHASE_01_02_GRANULAR_AUDIT.md) Phase 1 user checklist section

## Acceptance (Phase 1)

- [x] Continuity between `/studio/control/`, manager `/admin/`, `/super/*`
- [x] No duplicate primary chrome on manager Studio canvas (matrix)
- [x] Sidebar / nav role-aware where specified (superuser admin link)
