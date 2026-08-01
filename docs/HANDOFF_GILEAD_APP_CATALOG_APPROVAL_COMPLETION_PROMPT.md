# Gilead App Catalog approval-completion implementation prompt

Use this prompt for any implementation or release follow-up. Do not reinterpret or redesign the approved surface.

## Objective

Audit first, then complete and verify the tenant App Catalog and every shared dependency it uses. Treat the following file as the immutable visual and behavioral source of truth:

- `var/design-previews/gilead-tenant-configuration-operations-before-after-approval-2026-08-01.html`

Do not stop at source-code assertions. Verify the authenticated tenant surface through a real tenant hostname. The canonical route is `/settings/app-catalog/`; host routing must resolve a `TenantAdminSite`/tenant portal context and must never fall through to an operator or unknown-campus surface.

## Required audit before editing

1. Compare the approval HTML with the rendered tenant page, template inheritance, partial ownership, stylesheet order, JavaScript ownership, query/filter logic, marketplace seed data, publisher verification, plan entitlements, platform-release compatibility, tenant scoping, static resolution, service-worker cache state, and database migration state.
2. Record exact root causes. Distinguish genuine incompatibility from false warnings. Never hide a valid incompatibility merely to make the page look healthy.
3. Preserve already-correct components and actions. Do not rebuild working installation, scope-consent, sandbox, activation, billing, uninstall, rollback, or interoperability flows.

## Approved App Catalog contract

- One visible H1: `School App Catalog`.
- Eyebrow: `Governed capability marketplace`.
- Purpose: `Browse by outcome, validate trust at a glance, and open details only when you need them.`
- Full-width tenant canvas with no left-aligned narrow content column.
- Masthead stats for available apps, distinct verified publishers, and installed apps.
- Genuine `Installed apps` and `Review sandbox queue` actions.
- Two-part readiness area: `Install readiness` and `Your operating policy`.
- One server-owned GET filter bar containing search, outcome, pricing, and sort controls.
- Compact app grid: three columns above 1024px, two columns from 721px through 1024px, and one column at 720px and below.
- Cards show app identity, publisher trust, lifecycle, concise outcome copy, scope/pricing/sandbox metadata, collapsed `Compatibility & rollback`, and genuine `Review & install` plus `Scope` actions.
- Do not use broken remote preview images. Do not replace governed server-rendered cards with client-generated placeholder cards.
- Details remain collapsed by default. Remove oversized proof heroes, repeated plan counters, duplicated section navigation, expanded manifest dumps, simulated actions, duplicate shell chrome, and empty right-side space.
- All stylesheet links are owned by `<head>`. No inline style attributes, duplicate CSS URLs, raw icon names, unexpected fixed overlays, or horizontal page overflow.
- Light and dark themes must retain readable contrast on the tenant command canvas.
- Primary catalog inventory must never depend on a scroll-reveal animation for visibility.

## Compatibility rules that must remain enforced

1. Compare a school plan by canonical `Plan.slug`, not `str(plan)` or its display name.
2. Normalize current plan slugs and legacy manifest aliases to the commercial ladder `free`, `pro`, and `enterprise`. In particular:
   - `sovereign-self-hosted` satisfies `enterprise`.
   - a current Pro plan such as `growing-school` satisfies the legacy manifest alias `standard`.
3. Keep product semver and calendar releases separate:
   - `APP_VERSION` is product semver, currently `3.2.1`.
   - `RMC_RELEASE_VERSION` is the calendar release used by marketplace floors, currently `2026.08`.
   - A floor such as `2025.03` must compare with `RMC_RELEASE_VERSION`, never with `APP_VERSION`.
4. Preserve genuine blocks for missing features, a truly insufficient plan, an actually old platform release, unverified publishers, sensitive scopes, billing prerequisites, or a kill switch.
5. Compatibility checks are read-only. They must not mutate tenant state while browsing.

## Functional ownership

- Django owns listing visibility, tenant scope, search/filter/sort results, pagination, compatibility signals, entitlements, and genuine action URLs.
- JavaScript may debounce and submit the GET filter form and handle the existing install-impact modal. It must not `fetch()` a simplified public catalog and replace Django cards or actions.
- Install remains sandbox-first. Scope approval and activation remain separate deliberate operations. Paid manifests use the genuine billing/purchase path; free or included apps must not simulate checkout.

## Required validation

Run and require green results for:

```console
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py collectstatic --dry-run --noinput
python scripts/verify_template_compiles.py
python scripts/verify_django_admin_canvas_templates_compile.py
python scripts/verify_tenant_configuration_operations_build_lock.py
python scripts/audit_full_canvas_catalog_contract.py
python scripts/verify_marketplace_catalog_10x_closure.py
python scripts/verify_service_worker_version.py
python scripts/verify_platform_surface_layout_contract.py
python scripts/audit_tenant_surface_scroll_contract.py
python scripts/audit_platform_long_surface_contract.py
python scripts/audit_platform_surface_sweep.py
python scripts/verify_django_admin_preview_parity.py
python scripts/audit_django_admin_canvas_contract.py
python scripts/verify_admin_os_three_click_sla.py
python scripts/audit_django_admin_surface_leftovers.py
python scripts/sweep_django_admin_platformwide_layout.py
python scripts/audit_django_admin_miss_nothing.py
python manage.py test apps.marketplace.tests.test_tenant_app_catalog_approval apps.marketplace.tests.test_tenant_app_catalog_template_hierarchy apps.marketplace.tests.test_app_catalog_world_class_ux apps.marketplace.tests.test_app_catalog_apple_class_ux apps.marketplace.tests.test_tenant_catalog_magic_ux_strict apps.marketplace.tests.test_magic_ux_catalog apps.marketplace.tests.test_catalog_install_app_deeplink apps.marketplace.tests.test_app_scope_consent apps.marketplace.tests.test_manifest_platform_catalog apps.platform_runtime.tests.test_tenant_configuration_operations_closure apps.platform_runtime.tests.test_tenant_school_configuration_center --keepdb
python manage.py test apps.observability.tests.test_friction --keepdb
node scripts/verify_tenant_configuration_operations_browser.mjs
git diff --check
```

The real-host browser matrix must cover `/school/settings/`, `/school/configuration/`, `/academics/`, `/portal/offline-sync/`, `/finance/`, `/settings/app-catalog/`, and `/compliance/` at 1440, 1024, 768, and 390px in light and dark themes. For every route assert HTTP 200 after valid canonical redirects, correct hostname/scope, one visible H1, zero horizontal overflow, no broken resources, no duplicate CSS, no stylesheet in body, no unexpected fixed overlay, no raw icon names, and working form/action ownership. App Catalog evidence must additionally assert the approved column count, immediately visible cards, one filter form, no legacy proof hero, collapsed disclosures, genuine install/scope actions, the requested theme equals the resolved HTML theme, heading contrast is at least 4.5:1, and absence of the two false Gilead warnings. A normal `eventsource` `ERR_ABORTED` caused only by the audit closing an already-successful live stream may be classified as lifecycle cancellation; HTTP errors and every other failed request remain failures. The responsive sentinel's `layout_overflow` event must be accepted by the Django friction endpoint.

## Release seal and deployment

When any relevant static/template behavior changes, bump the tenant build ID, cache-bust ID, and service-worker version together and update both tenant and Django-admin locks. Never reuse a service-worker version.

After tests pass, commit only the scoped files and push without force. Production release steps are:

```console
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

Restart application workers, invalidate CDN/static caches, verify the new service-worker version, and rerun the authenticated matrix on `gilead-tech.runmycampus.com`. Report root causes, changed files, exact test counts, artifact paths, commit SHA, push result, and any external deployment action still required. Do not claim production is fixed until the deployed Gilead hostname passes.
