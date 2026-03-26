# Phase 3 — Navigation + command + page archetypes — checklist

**SOT:** Primary 8-pill nav + search **DONE** (ZIP Phase 1). Archetype attrs (`data-page-archetype`, decision zones) — **expand continuously**.

## Python

- [x] `apps/schools/control_plane_nav.py` — `build_primary_control_plane_nav()`, sidebar registry
- [x] `apps/schools/tests/test_primary_control_plane_nav.py`
- [x] `apps/schools/tests/test_control_plane_nav_roles.py`

## Templates — command / search

- [x] `templates/control_plane_base.html` — Ctrl+K, `#cpSearchInput`
- [x] `templates/admin/base_site.html` — manager search + shortcuts
- [x] `templates/studio_os/partials/shell_main_content.html` / `shell.html` — Studio palette

## Page archetypes (sample audit)

- [ ] Grep `data-page-archetype` coverage on new authenticated pages; add when missing
- [ ] `templates/schools/partials/decision_architecture_attrs.html` — include on decision surfaces

## Validation

- [x] Primary nav tests (see Phase 1 checklist)
- [ ] Document common click-path reductions when changing nav (execution log)

## Acceptance

- [x] Primary nav matches product buckets (Home, Studio, Operations, …)
- [x] Command palette / intent search on manager control plane + admin + Studio
- [ ] All major new pages declare archetype + decision zones where applicable
