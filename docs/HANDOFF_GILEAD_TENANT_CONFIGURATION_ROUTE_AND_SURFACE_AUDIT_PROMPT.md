# Gilead tenant configuration, route integrity, and full-canvas surface closure prompt

## Objective

Audit first, then repair the reported Gilead tenant defects and every operator-wide or tenant-wide recurrence of the same root causes. Do not treat a green health row, a redirect, or a source-code assertion as proof that a user workflow works.

The approved visual source of truth, once the user explicitly approves it, is:

- `var/design-previews/gilead-tenant-configuration-operations-before-after-approval-2026-08-01.html`

Until approval, do not apply its App Catalog, Finance, Academics, Offline Sync, or Configuration production markup/CSS. Functional route, scoping, data-integrity, and regression-test repairs may proceed only when they do not silently choose an unapproved visual design.

## Audited facts that must be reproduced before editing

Use the real hostname, not only `127.0.0.1`:

- `https://gilead-tech.runmycampus.com/academics/` returns HTTP 404.
- `https://gilead-tech.runmycampus.com/portal/offline-sync/` returns HTTP 404.
- `https://gilead-tech.runmycampus.com/portal/offline/sync-queue/` is the working canonical Offline Sync route.
- Signed-out requests to `/school/settings/`, `/school/configuration/`, `/settings/app-catalog/`, `/finance/`, and the canonical Offline Sync route redirect to Gilead's tenant login with a same-host `next` parameter.
- Four of the fourteen actions in `TENANT_CONFIGURATION_SECTIONS` point at non-resolving paths:
  - Academic Year / Term → `/siteconfig/academic-years/`
  - Classes / Subjects → `/academics/`
  - Offline Settings → `/portal/offline-sync/`
  - Security / Audit → `/compliance/`
- `apps/academics/urls.py` has no empty-path route.
- `apps/portal/urls.py` owns Offline Sync at `offline/sync-queue/`.
- `apps/compliance/urls.py` owns its entry page at `dashboard/`.
- `apps/schools/setup_health.py` awards the 25-point runtime check only from legacy `School.default_dashboard_slug` or `School.default_workflow_slug` fields.
- The provisioning path calls `assign_default_dashboard_packs(...)`, which creates real `DashboardPackAssignment` and `TenantLayoutAssignment` rows instead of filling those legacy slugs. This can make a correctly assigned school display 75% readiness.
- `templates/components/rmc_metric_ticker.html` uses `{% firstof metric_items metrics as tmval %}`. Django stringifies the selected list when assigning it; the later loop iterates characters. In an authenticated 1440px browser render, Finance's ticker became 8,925px tall and created hundreds of empty KPI cards. Analytics includes the same component.
- `templates/partials/cockpit/_operator_incident_banner.html` uses the same unsafe `firstof ... as` pattern with dictionary objects and must be tested on both hosts.
- `templates/partials/portal_sidebar_v8_groups.html` uses `{% regroup PORTAL_SIDEBAR_ITEMS by section %}`. `regroup` only merges adjacent records. A tenant-defined `portal_sidebar_order` that interleaves sections produces repeated group headings.
- App Catalog expands trust, compatibility, entitlements, rollback, install instructions, and next steps inside every listing. It also trusts `preview_image_url`/`screenshot_urls` without a browser-verified fallback when the remote asset fails.
- Finance currently renders a real masthead H1 plus an injected visually-hidden H1. The page must have one semantic page H1 and no duplicate visible/assistive page title.

Re-run these observations and save machine-readable evidence before changing code. If the current behavior differs, record the difference and explain why; do not overwrite the audit premise without evidence.

## Non-negotiable operating rules

1. Inspect `AGENTS.md` and the current dirty worktree before editing. Preserve unrelated user/agent changes. Do not reset, discard, or commit work outside this closure.
2. Resolve Gilead as tenant ID `f984ea95-d2ad-4900-b513-66a345928316`, slug `gilead-tech`. Never substitute a similarly named local fixture when changing production data.
3. Test tenant and operator hostnames separately because host routing selects different URLconfs, middleware, cookies, scopes, and admin sites.
4. Readiness must be evidence-backed. Never force 100%, seed fake slugs, hide a blocker, or label a missing dependency healthy.
5. Prefer named route ownership and `reverse()` over hand-authored literal paths.
6. Backward-compatible URLs may redirect only to a real, authorized canonical surface on the same tenant host. Preserve safe query parameters and reject unsafe external `next` targets.
7. No tenant surface may expose operator, fleet, Studio, invite-school, cross-tenant, or `/super/` actions.
8. No production button may be simulated. Wire it to a scoped GET/POST workflow with CSRF, authorization, audit, success/error states, and idempotency as applicable, or remove it.
9. All stylesheet links belong in `<head>`. Avoid inline production CSS/JS unless the repository's CSP-nonce contract explicitly requires it.
10. If static assets change, bump the build ID, cache-bust ID, and service-worker version together and prove monotonicity.
11. Do not commit screenshots containing secrets, session cookies, MFA material, student PII, or production credentials.

## Phase 1 — route and configuration action repair

### 1.1 Establish canonical route ownership

- Add a named tenant Academics root owned by `apps.academics` or a narrowly justified same-host redirect to the approved Academics hub.
- The root must be authorized, tenant-scoped, have one H1, full tenant chrome, and provide real routes for academic years/terms, classes, subjects, teaching assignments, timetable, attendance, grading, and syllabi as permissions allow.
- Add a backward-compatible named alias for `/portal/offline-sync/` that redirects to `portal:offline_sync_queue`. Keep `/portal/offline/sync-queue/` canonical.
- Do not create a second Offline Sync view or duplicate its JavaScript ownership.
- Do not make `/compliance/` a false content surface if `/compliance/dashboard/` is canonical. Either add a deliberate same-host named redirect or update every owner to reverse the dashboard name.

### 1.2 Eliminate literal path drift in Configuration

Refactor `TENANT_CONFIGURATION_SECTIONS` so action ownership is expressed by route name (and optional kwargs/query), not only a literal path. Resolve route names in the request's tenant URLconf and fail closed with an actionable diagnostic if a route cannot reverse.

Map the four stale actions to verified named owners:

- Academic Year / Term → the supported tenant academic-year setup/evidence route, currently `siteconfig:academic_years_setup_evidence` if that remains the canonical owner.
- Classes / Subjects → the approved named Academics root.
- Offline Settings → `portal:offline_sync_queue`.
- Security / Audit → `compliance:dashboard` or its actual namespaced equivalent.

Add a registry test that iterates every visible Configuration action for representative tenant roles and asserts:

- `reverse()` succeeds under `config.tenant_urls`;
- a GET on the tenant hostname returns 200 or an intentional permission/login response, never 404/500;
- the final hostname stays tenant-scoped;
- normal tenant administrators never resolve to manager or `/super/` surfaces;
- an action labeled healthy does not lead to a missing feature.

Scan other registries, help journeys, quick access, command palette, next-action strips, sidebar items, dashboards, emails, and docs-backed UI for the stale paths. Fix active runtime references; do not rewrite archived documentation merely to hide history.

## Phase 2 — honest readiness and provisioning evidence

Create a single tested runtime-assignment evidence service. It must use the active runtime model, in this order where applicable:

1. effective per-user/role dashboard preference;
2. active `TenantLayoutAssignment` for the school and required role set;
3. active `DashboardPackAssignment` for the school and required role set;
4. supported workflow pack/assignment evidence;
5. legacy dashboard/workflow slugs only as an explicit compatibility fallback while old tenants are migrated.

Update `setup_health_score`, `next_best_action`, Configuration readiness, tenant operational lifecycle, sync manifest, onboarding, and every other caller found by repository search to consume the same evidence service.

For Gilead:

- inspect plan, branding, dashboard pack, tenant layout, workflow assignment, academic year/term, roles, data migration, and provisioning Phase A/Phase B state;
- run the existing idempotent provisioning/reconciliation service when evidence is genuinely missing;
- create a narrowly scoped idempotent repair command only if no supported reconciler exists;
- support `--school-id`, `--school-slug`, `--dry-run`, structured output, and an audit event;
- never mutate other tenants;
- after repair, re-query the authoritative rows and compute readiness again;
- report any real blocker that prevents 100% instead of falsifying the score.

Add regression coverage for:

- pack/layout assignment present and legacy slugs empty → runtime passes;
- no pack/layout/workflow and legacy slugs empty → runtime fails;
- legacy-only tenant → compatibility behavior is explicit;
- provisioning assigns enough active evidence for a newly created tenant to reach the intended score;
- a stale/inactive assignment does not count;
- queries are school-scoped and role-aware.

## Phase 3 — shared template/data-shaping defects

### 3.1 Metric ticker

Remove object selection through `firstof ... as`. Give the component one typed iterable input or use an object-preserving template construct. Render exactly the supplied items, cap the visual component to its supported maximum, and treat an invalid scalar/string input as an empty/error state in development rather than character data.

Validate Finance and Analytics with zero, one, four, and over-limit metric inputs. Assert DOM card count, labels/values, bounded computed height, one semantic H1, and no empty anonymous KPI cards. The component JavaScript may mirror metrics into the sticky pin, but must never mutate or multiply the full list.

### 3.2 Operator and tenant incident banner

Replace the dictionary-coercing `firstof ... as` pattern. Prove operator and tenant dictionaries retain `severity`, `text`, and `timestamp`. Assert one banner, correct host data attribute, working activity drawer, snooze and dismiss behavior, and no cross-host incident leakage.

### 3.3 Sidebar grouping

Build deterministic `PORTAL_SIDEBAR_GROUPS` in Python. Preserve the first configured appearance of a section and the configured order of items inside it, but accumulate all items with the same section into one group. Render that structure directly; do not rely on adjacency-sensitive `regroup`.

Test:

- default order;
- deliberately interleaved `portal_sidebar_order`;
- pinned/current items;
- permission-filtered items;
- 390/768/1024/1440 widths;
- one visible group heading per section;
- no duplicated navigation in desktop/mobile DOM that becomes simultaneously visible;
- no tenant-visible `/super/`, fleet, operator Studio, invite-school, or cross-tenant links.

## Phase 4 — approved full-canvas surface implementation

Do this phase only after explicit approval of the referenced HTML.

### Configuration

- Use the full available canvas.
- Keep readiness evidence and route ownership visible without turning the page into an unbounded table.
- Show 100% only when the repaired evidence service returns 100.
- Every action must reverse to a valid scoped route and survive GET/POST workflow validation.

### App Catalog

- Replace the oversized proof slab with the approved compact command-center hero, policy/readiness band, filter toolbar, and responsive card grid.
- Keep trust and install posture glanceable. Put compatibility, rollback, and long explanations in accessible disclosures or a real detail view.
- Preserve sandbox-first install, scope consent, entitlement, purchase-intent, activation, uninstall, and rollback behavior.
- Validate all listing image URLs server-side where feasible and add a local static fallback for browser load errors. Broken remote assets must not show broken-image chrome.
- Escape API-rendered text. Do not build unsafe `innerHTML` from untrusted listing data; use DOM text nodes or a safe rendering contract.
- Ensure search/facets update result counts and preserve a functional server-rendered fallback.

### Finance

- Remove the metric multiplication defect before changing layout.
- Implement the approved bounded bento layout: four real KPIs, collections trend, aging, next actions, recent activity, and control posture.
- Empty datasets must show meaningful empty states in the same grid position, not hundreds of skeleton cards or a giant void.
- Keep invoice, fee generation, payment, reconciliation, trial balance, readiness, and export actions genuine and permission-scoped.
- Reduce to one semantic page H1.

### Academics

- Implement the approved root hub as a real tenant surface, not a marketing placeholder.
- Derive counts and health from tenant-scoped academic models.
- Empty schools receive guided setup actions, not fake metrics.

### Offline Sync

- Keep the canonical queue implementation and approved full-canvas information architecture.
- Show real queue, conflicts, device posture, encryption/key state, retry/replay, and audit evidence.
- Grades and payments require manual conflict review; tied timestamps must never silently overwrite.
- Replay/retry must be idempotent, scoped, authorized, CSRF-protected, and audited.

## Phase 5 — platform-wide recurrence sweep

Search and test, at minimum:

- every `firstof ... as` whose candidates may be a list, dict, queryset, model, or other object;
- every include of `rmc_metric_ticker.html`;
- every use of adjacency-sensitive `regroup` after configurable sorting;
- every active literal link to `/academics/`, `/portal/offline-sync/`, `/siteconfig/academic-years/`, or `/compliance/`;
- every Configuration/Setup/Health registry action;
- every surface showing readiness from legacy fields while provisioning writes new assignment models;
- every App Catalog/marketplace card image and action;
- every module dashboard with empty data, skeletons, duplicate H1s, or content pushed thousands of pixels below the fold;
- operator and tenant shell navigation for host-only control leakage.

Include operator index, operator inner pages, tenant index, school settings, school configuration, App Catalog, Finance, Analytics, Academics, Offline Sync, compliance, setup/onboarding, guided actions, and Django admin links where these shared components appear.

## Phase 6 — migrations, static ownership, and cache integrity

- Run `python manage.py makemigrations --check --dry-run` before creating any migration.
- If a model change is truly required, create the smallest migration, inspect SQL/plan, apply locally, and test forward behavior. Do not create a migration for a data repair that belongs in an idempotent reconciliation command.
- Run `python manage.py migrate --plan` and apply required local migrations.
- Compile all changed Django templates.
- Run `collectstatic --dry-run --noinput` (or the repository-supported equivalent).
- Confirm CSS links are in `<head>`, no duplicate stylesheet URLs, and no body stylesheet links.
- If static files change, update build ID, cache-bust ID, and service-worker version in one change. Run the service-worker monotonicity audit and prove the deployed page references the new identifiers.

## Required validation

### Static and Django

Run the repository-supported forms of:

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py migrate --plan`
- Django template compilation for all changed/affected templates
- `python manage.py collectstatic --dry-run --noinput`
- admin/tenant preview-parity audit
- leftovers/dead-link audit
- platform-wide sweep
- miss-nothing audit
- service-worker monotonicity check
- targeted tests for routes, setup health, provisioning, metric ticker, incident banner, sidebar grouping, Catalog, Finance, Academics, Offline Sync, scoping, permissions, and host routing
- `git diff --check`

Do not claim a command passed if the repository uses a different command or the command was skipped. Record exact invocations, exit codes, and relevant output.

### Browser and real-host matrix

Validate 1440, 1024, 768, and 390px in light and dark themes on both a real tenant hostname and the real manager hostname. Use authenticated browser sessions supplied securely; do not log credentials, cookies, MFA secrets, or tokens.

For every valid scoped route assert:

- expected HTTP status (200 when authenticated; intentional login/permission behavior when signed out);
- correct final hostname and tenant/operator scope;
- exactly one semantic visible page H1;
- zero horizontal overflow;
- no element unexpectedly thousands of pixels below preceding content;
- no broken resources or failed listing images without fallback;
- no duplicate CSS URLs;
- no stylesheet links in body;
- no unexpected fixed overlays;
- no raw icon names;
- one visible navigation group per section;
- native/real data display rather than simulated controls;
- all primary and secondary actions reach the expected GET/POST workflow;
- form/replay/install actions enforce authorization, CSRF, tenant scoping, and audit behavior.

Specifically capture DOM/computed evidence for:

- metric card count and ticker height on Finance and Analytics;
- Configuration action hrefs and final responses for all 14 rows;
- Gilead readiness inputs and resulting score;
- sidebar group names/counts under Gilead's saved order;
- App Catalog card count, image fallback, filter behavior, disclosures, and install paths;
- Academics root and Offline legacy/canonical paths.

### Production deployment verification

After merge/deploy:

1. verify `/-/version/`, health, readiness, build ID, static asset hashes, and service-worker version;
2. wait for the deployed commit, not merely a green local build;
3. run signed-out route checks on `gilead-tech.runmycampus.com`;
4. use a secure authenticated Gilead session to validate every requested surface and all 14 configuration actions;
5. run the scoped Gilead reconciler in dry-run, inspect output, apply only if required, then re-run dry-run and readiness;
6. capture sanitized screenshots and DOM/computed evidence at all viewports/themes;
7. remove stale failure artifacts and retain only evidence tied to the deployed commit/build ID.

## Acceptance criteria

Closure is complete only when:

- `/academics/` is a working tenant-scoped hub or intentional same-host alias;
- `/portal/offline-sync/` safely reaches the canonical working queue;
- all 14 Configuration actions resolve and their underlying workflows work;
- Gilead readiness is 100% only because all required authoritative evidence is present;
- Finance and Analytics render the supplied metric count with bounded height and no empty card multiplication;
- operator and tenant incident banners retain and render structured data;
- configurable sidebar order never duplicates section groups;
- the approved App Catalog and Finance designs use the full canvas at desktop widths and collapse cleanly at 1024px and below;
- App Catalog images never show a broken-resource surface and all install/consent/purchase/activation actions remain genuine;
- one semantic visible H1, zero horizontal overflow, no broken resources, no duplicate stylesheet URLs, and no unexpected fixed overlays hold throughout the matrix;
- operator-only controls never leak to tenant pages;
- tests, migrations, static collection, cache/version checks, and real-host browser validation pass;
- the final report names root causes, changed files, production data operations, migrations, exact tests/results, deployment steps, deployed commit/build ID, and any remaining externally blocked item.

Do not stop at a prettier screenshot. Prove route ownership, data truth, host scope, action behavior, and post-deploy browser reality end to end.
