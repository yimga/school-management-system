# Django admin approval audit — 2026-07-20 V11

## Outcome

The operator and tenant Django admin shells now conform to the immutable
approval sources:

- `docs/HANDOFF_DJANGO_ADMIN_APPROVAL_HTML.md`
- `var/design-previews/django-admin-page-aware-full-fill-approval-2026-07-19.html`
- `var/design-previews/tenant-admin-config-engine-approval-2026-07-19.html`

The approval identity is synchronized as:

- build: `2026-07-20-v11`
- cache bust: `20260720-admin-preview-parity-v11`
- service worker: `sms-v4.05.164-admin-preview-parity-v11-2026-07-20`
- seal: `2026-07-20-preview-parity-sot`

The final evidence set contains 30 passing real-host reports and 50 V11
screenshots. No failed JSON reports remain.

## Root causes

1. Several shell generations were active at once. Shared Unfold chrome, the
   custom admin navigation bridge, per-page workspace markup, legacy preview
   drawers, repeated hidden sentinels, and specialized templates all attempted
   to own header/navigation/context behavior.
2. Some nested partials emitted stylesheet links at their include location.
   When included from body blocks, those links appeared in `<body>` and could
   be duplicated.
3. The live verifier used `127.0.0.1`, allowed soft passes, and exercised stale
   routes and simulated Preview controls. It could not prove manager-host and
   tenant-host dispatch.
4. Local production-shaped verification initially combined a no-reload Django
   process, an out-of-date collected-static manifest, and `runserver
   --insecure`. The latter bypassed WhiteNoise and made hashed manifest URLs
   appear missing. This explains why valid source changes could look as if they
   had not taken effect.
5. Build, cache-bust, and service-worker identifiers were not enforced by every
   audit from one lock; one platform contract still expected an obsolete cache
   token.
6. `ExperienceRegionApproval`, a cross-tenant governance record, was genuinely
   registered on `TenantAdminSite`.
7. ThemePack admin deliberately hid native CRUD and redirected to Studio.
   Specialized theme templates also leaked Studio links and emitted color CSS
   from body content.
8. Site Settings created a wrapper around its preview button before the button
   had a parent, causing a real JavaScript exception and breaking the compact
   Save action behavior.
9. Tenant page-aware outcome links could resolve operator/Studio/fleet targets.
10. Guided school action templates rendered a second visible H1 through the
    shared workspace metrics strip.
11. The operator bridge registry lagged behind `PlatformAdminSite` by 35
    registered models, and its completeness test resolved the admin namespace
    against the wrong URLconf and omitted MFA-verified operator state. The
    broader operator URL suite had the same stale authentication fixture.
12. The academics migration state contained real model drift. Migration `0069`
    was generated and applied; the final plan is empty.

## Repairs

- Retained separate `PlatformAdminSite` and `TenantAdminSite` dispatch and
  verified them through `manager.runmycampus.com` and
  `demo-school.runmycampus.com`.
- Enforced desktop grids:
  - operator: `minmax(0,1fr) minmax(9.2rem,17%) 2.35rem`
  - tenant: `minmax(0,1fr) minmax(9.5rem,18%) 2.35rem`
- Enforced one column at 1024px and below.
- Restored native Django tables and native ThemePack CRUD.
- Made compact split Save controls genuine and browser-tested.
- Removed simulated preview/popout behavior and stale fixed preview drawers.
- Made the right rail/tool strip page-aware.
- Kept operator CTAs on the operator index only.
- Removed Studio/fleet/invite/operator controls from tenant admin content and
  moved Studio approval rows to the operator site.
- Consolidated CSS ownership in `<head>` and removed repeated shell/sentinel
  output.
- Added a strict real-host Playwright matrix and replaced the soft localhost
  verifier with a strict wrapper.
- Completed the operator bridge registry and made its tests host- and
  MFA-aware.
- Synchronized build/cache/service-worker versions through the approval lock.
- Removed the obsolete non-strict localhost report, 109 superseded
  screenshots/logs, and nine failed intermediate reports.

## Exact admin-repair files

### Python and migrations

- `apps/academics/migrations/0069_alter_specialty_options_alter_room_bookable_resource.py`
- `apps/brand_experience/admin.py`
- `apps/schools/platform_admin_surface_bridges.py`
- `apps/schools/super_admin_bridge_registry.py`
- `apps/schools/tests/test_platform_admin_bridge_completeness.py`
- `apps/schools/tests/test_super_config_migration_urls.py`
- `apps/siteconfig/admin_model_outcomes.py`
- `apps/siteconfig/tests/test_admin_model_outcomes.py`
- `apps/siteconfig/tests/test_admin_preview_contract.py`
- `apps/siteconfig/tests/test_admin_ui_smoke.py`
- `apps/siteconfig/tests/test_theme_studio.py`
- `apps/studio_os/admin.py`
- `apps/studio_os/tests/test_admin_site_boundary.py`

### Verification and build control

- `package.json`
- `scripts/audit_django_admin_canvas_contract.py`
- `scripts/audit_django_admin_miss_nothing.py`
- `scripts/audit_django_surface_platformwide_contract.py`
- `scripts/sweep_django_admin_platformwide_layout.py`
- `scripts/verify_django_admin_canvas_live.py`
- `scripts/verify_django_admin_preview_parity.py`
- `scripts/verify_django_admin_real_host_matrix.mjs`
- `var/admin-approval-build-lock.json`
- `var/admin-surface-platformwide-sweep.json`
- `var/django_admin_miss_nothing_audit.json`
- `var/security-audit-baseline-service-worker-version.json`

### Static assets

- `static/css/admin-nav-bridge-tenant.css`
- `static/css/admin-platform-catalog.css`
- `static/css/rmc-admin-django-canvas-contract.css`
- `static/js/rmc-admin-workspace.js`
- `static/js/service-worker.js`

### Django admin templates

- `templates/admin/app_index.html`
- `templates/admin/base.html`
- `templates/admin/base_site.html`
- `templates/admin/change_form.html`
- `templates/admin/change_list.html`
- `templates/admin/components/color_palette_studio.html`
- `templates/admin/delete_confirmation.html`
- `templates/admin/delete_selected_confirmation.html`
- `templates/admin/includes/admin_workspace_metrics_strip.html`
- `templates/admin/index_superadmin.html`
- `templates/admin/index_tenant.html`
- `templates/admin/object_history.html`
- `templates/admin/schools/school/delete_guided.html`
- `templates/admin/schools/school/waive_subscription_form.html`
- `templates/admin/siteconfig/dashboarduserpreference/change_form.html`
- `templates/admin/siteconfig/dashboardwidget/change_form.html`
- `templates/admin/siteconfig/reportcardstyle/change_form.html`
- `templates/admin/siteconfig/sitesettings/change_form.html`
- `templates/admin/siteconfig/themepack/change_form.html`
- `templates/components/admin_nav_bridge.html`

### Shared head/shell partials

- `templates/partials/portal_row_detail_drawer_bundle.html`
- `templates/partials/rmc_authenticated_theme_tail.html`
- `templates/partials/rmc_dashboard_corporate_os_styles.html`
- `templates/partials/rmc_lexicon_meta.html`
- `templates/partials/rmc_platform_chrome_styles.html`
- `templates/partials/rmc_platform_shell_beautify_styles.html`
- `templates/partials/rmc_security_posture_layout_styles.html`
- `templates/partials/rmc_shortcuts_i18n.html`
- `templates/partials/rmc_sidebar_disclosure_contract_styles.html`
- `templates/partials/rmc_social_meta.html`
- `templates/partials/rmc_theme_experience_dual_plane_styles.html`
- `templates/partials/rmc_theme_meta.html`
- `templates/partials/rmc_theme_personality_overrides.html`
- `templates/partials/rmc_tour_bootstrap.html`

### Evidence lifecycle

- deleted: `artifacts/django-admin-canvas-live/report.json`
- added/retained: `artifacts/django-admin-canvas-live/real-host-*.json`
- added/retained: `artifacts/django-admin-canvas-live/2026-07-20-v11-*.png`

The worktree also contains pre-existing migration-cloud, offline, legal,
documentation, companion-extension, and platform-runtime changes. They were
preserved and are not claimed as part of this admin repair.

## Validation

### Browser/DOM/computed style

Both real hostnames passed at 1440, 1024, 768, and 390px in light and dark.
Covered routes include index, app index, changelist, add, change, history,
delete, delete-selected confirmation, guided school delete/waive, Site
Settings, Schools, registries, runtime defaults, ThemePack, compliance rules,
documents, migration runs, marketplace apps, education-system profiles, and
specialized admin templates.

For every exercised route the verifier asserted:

- HTTP 200 and correct browser hostname/scope
- one visible H1
- zero horizontal overflow
- no failed resource or console error
- no duplicate stylesheet URL
- no stylesheet link in body
- no unexpected visible fixed overlay
- no raw icon name
- native table display when a result table exists
- exact desktop grid or exact one-column responsive grid
- page-aware right rail and tool strip
- working compact split Save menu
- no tenant operator/Studio/fleet leakage
- no operator index CTAs on non-index pages

Evidence directory: `artifacts/django-admin-canvas-live/`

### Commands

- `python manage.py check`: pass
- `python manage.py makemigrations --check --dry-run`: no changes
- `python manage.py migrate --plan`: no planned operations
- actual `python manage.py collectstatic --noinput`: pass; 5 copied, 1320
  unmodified, 5966 post-processed
- final `collectstatic --dry-run --noinput`: pass; 0 copied, 1325 unmodified
- Django canvas template compilation: pass
- full template comparison: 1858 compiled, 0 failures
- admin preview-parity audit: pass
- admin leftovers audit: pass, 0 findings
- platform-wide sweep: pass, 0 findings
- miss-nothing audit: pass, 0 findings
- platform-wide Django surface contract: pass
- service-worker monotonicity: pass at v4.5.164
- targeted Django admin and operator URL tests: 44 passed
- bridge completeness: every registered operator model covered
- JavaScript/Python syntax checks: pass
- `git diff --check`: pass

The full repository test suite was not run; the 44 tests are the targeted
admin, registration-boundary, outcome-rail, preview-contract, bridge, and
operator URL suites named by this repair.

`collectstatic` reports expected source shadowing: Unfold supplies its admin
JavaScript before Django, while the repository intentionally overrides
`admin/js/change_form.js` and `unfold/js/chart/chart.js`. This is source
selection, not a duplicate browser request; the real-host resource and
stylesheet assertions pass.

## Production deployment

1. Back up the database and deploy the reviewed code plus migration `0069`.
2. Run `python manage.py migrate --plan`; review, then run
   `python manage.py migrate`.
3. Run `python manage.py collectstatic --noinput` against the production static
   storage.
4. Restart every Django web process so no no-reload worker retains old
   templates or Python registrations.
5. Invalidate the CDN/static edge for the old cache ID while retaining hashed
   assets long enough for in-flight pages.
6. Serve the new `service-worker.js`, confirm the V11 worker activates, and
   allow one reload for previously controlled clients.
7. Smoke-test `https://manager.runmycampus.com/admin/` and at least one real
   tenant `https://<tenant>.runmycampus.com/admin/` separately.
8. Run the strict real-host matrix with authenticated manager and tenant
   sessions. Do not substitute `127.0.0.1`.
9. Confirm the rendered build marker, cache ID, and worker version match the
   approval lock, and retain the new pass reports as release evidence.

## Reusable enforcement prompt

> Treat the Django admin approval handoff and both dated approval HTML files as
> immutable. Audit `PlatformAdminSite` and `TenantAdminSite` through real
> manager and tenant hostnames. Repair inheritance, template-block ownership,
> partials, stylesheet ordering, JavaScript ownership, static resolution,
> migrations, caching, and service-worker rollout. Require the locked operator
> and tenant grids, one column at 1024px and below, native Django tables,
> genuine compact split Save controls, page-aware tools, strict scope
> isolation, head-owned CSS, and synchronized build/cache/SW IDs. Exercise
> index, app index, CRUD, history, delete/delete-selected, guided actions,
> settings, schools, registries, and specialized templates at 1440/1024/768/390
> in light and dark. Prove HTTP/host/scope, one H1, no overflow or broken
> resources, no duplicate/body CSS, no fixed overlay or raw icon leak, native
> tables, and working form actions with DOM/computed-style evidence. Run every
> repository admin audit, Django migration/static/template gate, targeted test,
> service-worker monotonicity check, and `git diff --check`; remove stale failed
> evidence and report exact roots, files, results, and deployment steps.
