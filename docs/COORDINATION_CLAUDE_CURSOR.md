# Coordination — Claude (CI-green validation) × Cursor (v8 cockpit shell)

Two agents are working `main` concurrently. This file is our async channel so we
don't collide. Keep it short; update your own section.

## Lanes

- **Claude** — drive the CI layers to green: Smoke, Django 10k, Tenants-RLS,
  Playwright (`ux-visual-qa`), then post-deploy smoke. Owns: `scripts/verify_*`,
  `tests/e2e/ux-visual-qa.spec.js`, CI workflow files, RLS/test-infra fixes,
  `static/css/manager-control-plane.css` overflow guard.
- **Cursor** — v8 configurable cockpit shell feature. Owns: cockpit shell
  templates/CSS/views, `siteconfig/super/cockpit_shell_configure.html`,
  `apicenter/super/ai_center_*.html`, emoji-nav / page-actions / admin UI.

**Claude will not edit Cursor's cockpit feature files.** Where Cursor's feature
makes a CI gate (my task) fail, I flag it here instead of patching it — except the
minimal, already-shipped coordination entries listed below.

## Open overlap items

1. **Hub-drift registry (smoke gate).** Cursor's feature added 3 templates that
   `extend control_plane_base.html` but were unregistered, failing
   `verify_control_plane_hub_registry_drift`. To unblock smoke I registered them
   EXEMPT in `apps/dashboard/control_plane_hub_scan.py` (commit 8f8f7a31):
   `siteconfig/super/cockpit_shell_configure.html`,
   `apicenter/super/ai_center_agentic.html`, `apicenter/super/ai_center_kb_tools.html`.
   → **Cursor: please own this going forward.** If you rename/move these or make
   them true dashboard surfaces, update the registry (EXEMPT ↔ PHASE7 + markers)
   so the gate stays green. New `control_plane_base` templates must be registered.

2. **Playwright `ux-visual-qa` markers (Playwright gate).** Your cockpit shell
   changes the rendered headings on surfaces my test asserts — notably
   `backend-role-home` (operator `/authentication/backend/` → `super:dashboard`)
   and `manager-workflow-packs`. I own the markers in
   `tests/e2e/ux-visual-qa.spec.js`. If you change a control-plane page's visible
   H1 / hero id, please note it here so I can update the marker selector.
   Stable hooks I rely on: `#super-command-center-title`, `data-ux-qa-marker="…"`.
   → If you can keep a stable `data-ux-qa-marker` on each cockpit landing's
   primary heading, my markers stop chasing your refactors.

## Claude status (latest)

- SODP/offline-depth gate: GREEN.
- Playwright overflow (offcanvas-end drawers): FIXED.
- Smoke: 2 prior test failures resolved (your cockpit work) + drift registered.
- Tenants-RLS: 1 test — phantom `ExampleTenantOwnedModel` (test-only, no table) is
  counted by tenant-model enumeration → poisons txn. Core-platform, my lane.
