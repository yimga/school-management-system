# Gilead tenant configuration operations closure — 2026-08-01

## Scope and source of truth

This change implements the approved tenant configuration-operations canvas across the applicable tenant surfaces, while preserving tenant host routing and Django's authorization boundaries. The visual approval source is:

- `var/design-previews/gilead-tenant-configuration-operations-before-after-approval-2026-08-01.html`
- `var/design-previews/tenant-pack-setup-full-canvas-before-after-approval-2026-07-31.html`

The production tenant identity audited before implementation was school ID `f984ea95-d2ad-4900-b513-66a345928316`, slug `gilead-tech`, host `gilead-tech.runmycampus.com`. The local database does not contain that production record, so this work did not mutate production tenant data.

## Root causes closed

1. `/academics/`, `/portal/offline-sync/`, and `/compliance/` were linked as tenant destinations but did not have canonical tenant URL patterns. They returned 404 before authentication could reach the valid underlying pages.
2. Configuration readiness inferred dashboard/workflow state only from legacy `School.default_*_slug` fields. Provisioning writes current `DashboardPackAssignment`, `TenantLayoutAssignment`, and workflow assignment records, so healthy schools could remain at 75%.
3. Configuration action rows contained stale literal paths. The new catalog uses named tenant routes and fails closed when a route is unavailable.
4. Shared template components received structured objects but rendered them through scalar coercion. The metric ticker and incident banner consequently repeated or expanded into extremely tall content.
5. Sidebar regrouping was adjacency-sensitive and happened in templates. Repeated category runs produced duplicate navigation groups. Grouping is now deterministic server-side data.
6. Page-specific CSS and the row-detail drawer bundle had split ownership. Some child pages emitted duplicate stylesheet URLs or stylesheet links in `<body>`. Root shells now own the CSS in `<head>` and legacy child includes are safe no-ops.
7. Finance, configuration, academics, offline sync, compliance, and app catalog had no shared full-canvas operating layout. The approved responsive workbench, density, action hierarchy, and page-aware rail are now supplied by one tenant operations stylesheet.
8. The app catalog mixed template values into executable JavaScript and used long unbounded records. The interaction code is now static, reads JSON/data attributes, and uses accessible disclosure cards.
9. The asset build identifiers were not tied to this closure. Tenant and Django-admin build/cache locks and the service-worker version now advance together.

## Implemented surfaces and infrastructure

- Tenant routes and views: `apps/academics/urls.py`, `apps/academics/views_hub.py`, `apps/portal/urls.py`, `apps/compliance/urls.py`.
- Readiness and assignment evidence: `apps/schools/runtime_assignment_evidence.py`, `apps/schools/setup_health.py`, `apps/platform_runtime/views_administration.py`, `apps/platform_runtime/administration_catalog.py`.
- Safe scoped repair command: `apps/siteconfig/management/commands/assign_default_dashboard_packs.py` (dry-run by default; accepts `--school-id` or `--school-slug`).
- Shared structured rendering: `apps/platform_runtime/templatetags/rmc_component_tags.py`, `templates/components/rmc_metric_ticker.html`, and the cockpit incident-banner partials.
- Deterministic navigation: `apps/siteconfig/portal_sidebar_items.py`, `apps/siteconfig/context_processors.py`, and the portal sidebar partials.
- Approved tenant workbench: `static/css/rmc-tenant-configuration-operations.css` plus the configuration, academics, finance, offline-sync, compliance, and app-catalog templates.
- Genuine catalog interaction: `static/js/tenant-app-catalog.js`; simulated/no-op preview behavior was removed.
- Root-owned drawer assets: `templates/partials/portal_row_detail_drawer_bundle.html` and `templates/marketing/base_marketing.html`.
- Cache seal: `var/tenant-configuration-operations-build-lock.json`, `var/admin-approval-build-lock.json`, and `static/js/service-worker.js`.
- Permanent verification: browser/build-lock scripts and targeted Django tests under `apps/platform_runtime/tests`, `apps/portal/tests`, and `apps/marketplace/tests`.

## Validation evidence

- Real tenant-host browser matrix: 56/56 results pass across seven routes, widths 1440/1024/768/390, and light/dark themes.
- Every matrix result asserts correct tenant hostname/scope, HTTP success after valid redirects, one visible H1, zero horizontal overflow, no failed resources, no duplicate CSS URL, no stylesheet in body, no unexpected fixed overlay, and no raw icon name.
- Django regression sets: 64/64 and 109/109 pass (173 applicable tests total), including tenant isolation, readiness, provisioning/lifecycle, catalog, finance/offline surfaces, navigation, incident banner, and 1/7/14/30-day MFA trusted-browser behavior and revocation.
- `manage.py check`: pass.
- `makemigrations --check --dry-run`: no changes.
- `migrate --plan`: no planned migrations in the audited local environment.
- `collectstatic --dry-run --noinput`: pass; only pre-existing third-party duplicate-name notices were emitted.
- Django admin template compilation, approval-preview parity, leftovers, platform-wide, miss-nothing, canvas, tenant-scroll, long-surface, platform-surface, and row-drawer audits: pass with zero findings.
- Build-lock and service-worker monotonicity checks: pass.
- Evidence JSON:
  - `artifacts/design-approvals/gilead-configuration-surface-audit-2026-08-01/pre-implementation-audit.json`
  - `artifacts/design-approvals/gilead-configuration-surface-audit-2026-08-01/post-implementation-browser-matrix.json`

## Production deployment and Gilead readiness reconciliation

Run the normal production release from this commit, then:

```console
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py assign_default_dashboard_packs --school-id f984ea95-d2ad-4900-b513-66a345928316 --json
python manage.py assign_default_dashboard_packs --school-id f984ea95-d2ad-4900-b513-66a345928316 --apply --json
```

The first assignment command is a read-only preview. Review its selected pack/layout assignments before applying. After the scoped apply, restart application workers and clear/roll CDN caches so service worker `sms-v4.06.25-tenant-configuration-operations-2026-08-01` is served. Then authenticate on the actual Gilead hostname and repeat the seven-route matrix. Readiness reaches 100% only when the production tenant has real active assignment evidence; the UI no longer manufactures a healthy status from stale fields.
