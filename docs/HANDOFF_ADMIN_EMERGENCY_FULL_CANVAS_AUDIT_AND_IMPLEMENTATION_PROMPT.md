# Django admin emergency full-canvas audit and implementation prompt

Status: **approved and implemented locally on 2026-08-09**. The user explicitly approved the browser artifact and made complete tenant-wide/operator-wide implementation non-negotiable.

Approval artifact:

- `var/design-previews/admin-emergency-full-canvas-and-provisioning-before-after-approval-2026-08-09.html`

Approval evidence:

- source/registry/cascade round: `var/admin-emergency-surface-audit-2026-08-09.json`;
- Chromium browser round: `var/admin-emergency-approval-browser-proof-round-2.json`;
- installed Microsoft Edge browser round: `var/admin-emergency-approval-browser-proof-round-3-edge.json`.

The approval source round completed against build `2026-08-08-v16.4`. Both independent approval-browser rounds passed at 1440×1000, 1024×900, 768×900 and 390×844 with zero horizontal overflow and zero console errors. They exercised every preview tab, both before/after modes, theme switching and the conditional configuration recommendation. The implemented v17 contract is validated separately against real manager and tenant host routing.

The implemented repair is build `2026-08-09-v17.1`, cache-bust `v171`, service worker `sms-v4.06.33-admin-full-canvas-2026-08-09`, and canvas seal `2026-08-09-admin-os-v171-full-canvas`. Production-shaped browser validation uses independent `manager.runmycampus.com` and `gilead-tech.runmycampus.com` Host headers, independent scoped sessions, all four required viewport widths, and both themes.

Final local implementation result:

- all three post-fix source/cascade re-audit rounds passed;
- the registry audit covered 471 registered models, 89 admin templates and 319 CSS files, with one terminal layout owner, zero theme-coupled admin surfaces, zero hard-white blockers and zero unnonced admin inline scripts;
- the core real-host matrix passed 216 route/viewport/theme evaluations (27 operator-and-tenant routes across 1440, 1024, 768 and 390 pixels in both themes);
- the specialized registry-derived matrix passed every valid scoped form surface at 1440 dark and 390 light, with exclusions recorded by permission/scope instead of counted as passes;
- the signup and guided-onboarding browser matrix passed all 14 cases;
- Django checks, migration checks/plans, collection dry-run, 1,878-template compilation, preview parity, leftovers, platform sweep, miss-nothing, service-worker monotonicity and `git diff --check` passed;
- the final focused Django suite passed 21/21 tests, including tenant/operator MFA trust periods and signup migration-recommendation persistence.

Implementation evidence:

- one terminal admin geometry owner: `static/css/rmc-admin-emergency-full-canvas-v17.css`;
- one page-awareness owner: `static/js/rmc-admin-page-aware-v17.js`;
- semantic Django fieldset and compact split-save overrides: `templates/admin/includes/fieldset.html` and `templates/admin/submit_line.html`;
- global hard-white escape-hatch protection: `static/css/rmc-theme-surface-safety-v1.css`;
- balanced progressive signup: `static/css/rmc-signup-balanced-v3.css`, `static/js/rmc-signup-balanced-v3.js`, and `templates/schools/signup_school.html`;
- deterministic, recommendation-only onboarding manifest v3 with no silent entitlement activation: `apps/schools/onboarding_recommendations.py`;
- real-host session and browser gates: `scripts/export_django_admin_real_host_sessions.py`, `scripts/verify_django_admin_real_host_matrix.mjs`, and `scripts/verify_signup_balanced_real_browser.mjs`.

Immutable prior direction:

- `docs/HANDOFF_DJANGO_ADMIN_APPROVAL_HTML.md`
- `var/design-previews/django-admin-page-aware-full-fill-approval-2026-07-19.html`
- `var/design-previews/tenant-admin-config-engine-approval-2026-07-19.html`
- `var/design-previews/django-admin-os-top-tier-approval-v15-2026-07-21.html`

## Pre-fix audit conclusion

The approved design direction existed in source, but did not have exclusive ownership of the rendered admin surface. `templates/admin/base_site.html` activated four layout generations: workspace-10x, canvas-contract, an inline preview-parity critical block, and approval-v15. Specificity and load order therefore changed the winner between pages.

The previous “platform-wide” gates were also structurally incomplete. They selected stylesheet files by words in filenames and scanned direct `admin/base_site.html` extenders. The pre-fix inventory had 315 CSS files, 88 admin templates, 197 operator registrations and 274 tenant registrations. A wrapper-width assertion could not detect the reported white card, narrow real widgets, mile-long sections, repeated navigation or low canvas occupancy.

Source inventory found:

- 32 copied specialized-admin guidance cards that use a light utility background coupled to a `dark:` variant;
- 8 hard-white template lines without a same-line dark alternative, including Studio OS and Siteconfig graph mounts;
- four concurrent admin layout owners;
- seven inline admin script blocks without a nonce;
- operator forms with up to 119 concrete fields and tenant forms with up to 38 fields;
- long native relations and inlines whose inner widgets are not measured by current browser gates.

The school signup flow is not empty. It already captures country, languages, education cycles, funding type, organization scope, student capacity, LMS preference and migration intent, then stores a deterministic recommendation manifest. The missing layer is a complete, auditable configuration autopilot: high-impact conditional operating inputs, versioned blueprint resolution, an explainable subscription recommendation, confirmation/override audit and safe recomputation.

## Approved implementation contract

Treat this handoff, the new approval artifact, and the prior approval sources as immutable visual and behavioral truth. Audit first, preserve the complete repair, validate three times, then commit and push to `main` only when all required evidence is green.

### 1. Establish one owner

Trace `BaseRunMyCampusAdminSite`, `PlatformAdminSite` and `TenantAdminSite`, every base/change/list/index/action template, all stylesheet links, inline style blocks, JavaScript owners, static resolution and service-worker caches.

Replace the four competing layout generations with one versioned, final admin surface owner. Older CSS may retain tokens or isolated components, but may not own shell tracks, primary workspace grids, form field placement, rails, tool strips, submit rows, tables, page width or responsive behavior. Remove the inline critical layout duplicate after equivalent external ownership is proven. Add a gate that fails when multiple files/layers own those selectors.

Keep all CSS links in `<head>`. Keep operator-only controls out of tenant pages. Keep operator index CTAs on the operator index only. Remove duplicate shell, header, breadcrumb, navigation, context drawer, footer and fixed overlay instances.

### 2. Generate the real route matrix

Build audit coverage from both live AdminSite registries, not a manually curated route list. For each registered model, resolve every permission-valid surface that exists:

- index and app index;
- changelist and search/filter states;
- add and change;
- history and delete;
- delete-selected confirmation;
- object tools and guided actions;
- inlines, `filter_horizontal`, autocomplete, file/date/color/JSON/textarea widgets;
- specialized templates, Site Settings, Schools, registries and Runtime Defaults.

Run operator and tenant hosts independently because host routing selects different admin sites. Record skipped routes with the exact permission or fixture reason; do not count a skip as a pass.

### 3. Implement the approved page-aware canvas

Enforce above 1024px:

- operator: `minmax(0,1fr) minmax(9.2rem,17%) 2.35rem`;
- tenant: `minmax(0,1fr) minmax(9.5rem,18%) 2.35rem`.

At 1024px and below use one column and move contextual rail content into accessible disclosure/flow content. Keep full native Django tables and tabular inlines. Keep compact split Save actions. Tool strips and rails must be page-aware and contain only genuine actions.

Create explicit field strategies derived from widget/model semantics:

- short fields: dates, years, booleans, small enums;
- standard fields: names, codes, email, phone, simple relations;
- wide fields: URLs, addresses, search, JSON, long text, permission selectors;
- full-canvas structures: native tables, horizontal relations, tabular inlines and rich builders.

Do not use a universal narrow `max-width` on inputs. Assert actual input/select/textarea rectangles against the primary column, not only their wrapper.

For long forms, provide page-specific section architecture. Runtime Defaults, Site Settings, School, User, Student Profile and other high-field forms must expose meaningful sections with search/index/disclosure so normal work does not require traversing an always-open multi-screen stack. Preserve all native fields and submissions.

### 4. Eliminate white/high-contrast blockers codebase-wide

Replace copied `bg-base-50 dark:...`, `bg-white`, inline white backgrounds and other mode-coupled escape hatches with semantic components/tokens whose foreground, background, border, focus and disabled states are resolved by the same theme authority.

Start with every instance recorded by `scripts/audit_admin_emergency_surface_contract.py`, including all 32 specialized admin cards and the Studio OS/Siteconfig graph mounts. Expand the scan to rendered components and dynamically added markup. Do not blindly recolor media, printable documents or deliberately white content; classify and test each exception.

Add dark and light computed-style assertions for:

- luminance/contrast of panels, text, links, badges and controls;
- no unexpected near-white surface inside a dark shell;
- no transparent foreground over mismatched inherited background;
- chart/graph canvases with explicit palettes;
- focus, error, warning, success and disabled states.

### 5. Repair ownership of behavior

Move page behavior out of specialized inline scripts into nonce-safe, versioned modules. One module owns section switching, compact Save, back navigation, preview and page-aware rails. Preview/popout actions must perform a real action or be removed. Do not locate submit rows with broad `[class*="submit"]` fallbacks.

### 6. Upgrade signup to configuration autopilot v4

Preserve the existing simple signup. Use progressive disclosure and ask only questions that change a deterministic output. Add conditional inputs for:

- campus and staff scale;
- boarding/day, hostel and transport operations;
- fee collection and payment rails;
- assessment/regulatory path;
- connectivity/offline reliability;
- identity/SSO and current-system complexity;
- go-live timeline and migration depth;
- data residency, accessibility and special-education requirements when relevant.

Resolve actual versioned IDs for blueprint, modules, grading profile, languages, dashboard/workflow packs and migration packs. Recommend a subscription SKU with rationale, confidence, cost/upgrade boundary and missing-input explanation. A recommendation must never silently grant a paid entitlement. Require confirmation; persist recommendation version, answers, confirmation, overrides and override reason in the audit trail. Recompute deterministically when an input fingerprint changes and protect operator-locked decisions.

Implementation reference: `docs/TENANT_CONFIGURATION_AUTOPILOT_V4.md`. Keep HTTP/form parsing, typed normalization, deterministic policy resolution and persistence as separate concerns. New inputs must be added to the typed boundary and its strict/legacy-repair tests before recommendation rules consume them.

### 7. Browser and deployment proof

At 1440, 1024, 768 and 390px in light and dark, assert for every valid scoped route:

- HTTP 200 and correct manager/tenant hostname and scope;
- exactly one visible H1;
- no horizontal document overflow;
- no broken resource, duplicate CSS URL or stylesheet in body;
- no unexpected fixed overlay or repeated navigation/footer/shell;
- no raw icon names;
- expected three-column grid above 1024 and one column at/below 1024;
- acceptable computed contrast and no hard-white blocker in dark mode;
- semantic control occupancy and reasonable page-length/section disclosure;
- native table/inline display and genuine form/action behavior.

Run three independent post-fix re-audits:

1. source/registry/cascade audit;
2. local real-host browser matrix with DOM, computed-style, network and interaction evidence;
3. deployed real-host fresh-session audit after cache and service-worker activation.

The third round must fetch and report the build ID, cache-bust ID and service-worker version from manager and tenant hosts. Bump all three together. Remove stale failure artifacts, rerun any failing route and retain exact screenshots/JSON evidence.

Run at minimum:

- `manage.py check`
- `makemigrations --check --dry-run`
- `migrate --plan`
- `collectstatic --dry-run`
- Django template compilation
- admin preview-parity audit
- admin leftovers audit
- platform-wide registry-driven sweep
- miss-nothing computed-style audit
- contrast/hard-white audit
- service-worker monotonicity check
- targeted Django and Playwright tests
- `git diff --check`

Report root causes, files changed, migrations applied, route counts, skips, screenshots, JSON evidence and production deployment steps. Commit intentionally and push to `main` after the local source, production-shaped real-host, and fresh-session browser audits prove the new identifiers and the complete contract. The real production deployment must then run migrations and collectstatic, restart application workers, activate the matching service worker, and repeat the fresh-session hostname matrix before release promotion.
