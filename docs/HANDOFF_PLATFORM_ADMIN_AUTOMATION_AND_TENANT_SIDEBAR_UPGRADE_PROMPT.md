# Platform admin automation and tenant sidebar upgrade — binding execution prompt

Use this prompt as an implementation contract. It authorizes repository-contained
code, tests, documentation, static rebuilds, migrations when genuinely required,
and a commit/push to `main`. It does not authorize invented production evidence.

## Mission

Audit first, then upgrade every applicable Django surface rendered from `/admin/`
on both the manager/operator hostname and each tenant hostname. Preserve the
approved page-aware full-canvas design and make the backend predictive,
low-friction, tenant-safe, resilient and genuinely operational. Add a serious
tenant-wide `/admin/` sidebar upgrade. Execute the work A–Z; do not stop after
writing this prompt or after source-only assertions.

## Immutable visual and behavioral references

- `docs/HANDOFF_DJANGO_ADMIN_APPROVAL_HTML.md`
- `var/design-previews/django-admin-page-aware-full-fill-approval-2026-07-19.html`
- `var/design-previews/tenant-admin-config-engine-approval-2026-07-19.html`
- `var/design-previews/admin-emergency-full-canvas-and-provisioning-before-after-approval-2026-08-09.html`
- `var/design-previews/tenant-admin-form-quality-before-after-2026-08-07.html`

Keep the existing terminal layout owner. Do not introduce a second shell, a
second sidebar, body-owned stylesheet, fixed blocking band, fake control, or a
parallel preference store.

## Stage 0 — mandatory audit before edits

1. Trace `PlatformAdminSite`, `TenantAdminSite`, their common base class,
   registration wrappers, template inheritance, partial inclusion, stylesheet
   order, JavaScript ownership, static resolution, cache busting, service worker,
   hostname URL-conf switching, tenant scoping and migration state.
2. Inventory index, app index, changelist, add, change, history, delete,
   delete-selected, guided actions, Site Settings, Schools, registries, inlines
   and specialized templates on manager and tenant hostnames separately.
3. Run broad and deep passes. Record every issue as:
   `surface -> root cause -> owner -> fix -> proof`.
4. Detect duplicated navigation, global browser keys, cross-host preference
   leakage, hidden current routes, dead links, repeated labels, raw icon names,
   broken resources, inaccessible controls, non-native tables, unbounded forms,
   manual system-owned fields, missing smart initials and incomplete validation.
5. Reuse current services and preferences before adding new architecture.

## Stage 1 — shared admin automation contract

Apply through the common admin-site registration/inheritance path so bespoke
admins cannot silently opt out.

- Suggested business values: server-prefilled, clearly recommended, editable;
  submitted user input always wins.
- Optional business fields: editable and user-selectable as visible/hidden.
- System evidence: server-bound and read-only, including tenant ownership,
  lifecycle actors/timestamps, hashes, tokens and security state.
- Bind tenant ownership from the resolved request hostname, never a posted FK.
- Forecast dates, names, sequences and defaults from scoped historical rows and
  existing provisioning engines. Never overwrite valid explicit input.
- Use native, keyboard-operable controls; dates must work without a JavaScript-
  only icon. Preserve current approved visual classes.
- Validate ranges, overlap, uniqueness, state transitions, permissions and
  cross-field dependencies before persistence and inside transactions where
  concurrency matters.
- Preferences must be server-persisted per user, hostname, admin site, model and
  add/change mode. Mandatory and conditionally mandatory fields cannot hide.
- Hidden values remain validated and cannot be changed by crafted unauthorized
  POSTs. Invalid or obsolete preference keys fail closed or are safely ignored.
- Handle empty history, malformed data, database unavailability, concurrent
  updates, offline retries and revoked permissions without data corruption.

## Stage 2 — binding tenant `/admin/` sidebar contract

The sidebar is a tenant operations instrument, not an unstructured app dump.

### Isolation and ownership

- Mount only under the tenant Django admin root. Operator assets and controls
  must not leak into it; tenant controls must not replace the operator sidebar.
- Persist navigation state in the existing server-owned user preference model,
  scoped by authenticated user + exact hostname + admin-site name.
- Browser storage is an offline retry envelope only. Keys must contain an opaque
  scope identifier; no browser-global pin, recent, collapse or section key.
- Only relative same-host `/admin/` paths may be stored. Reject schemes,
  authorities, control characters, oversized payloads, unknown keys and excess
  items. Mutations use authenticated `AdminSite.admin_view` plus CSRF-protected
  unsafe methods; GET stays side-effect free.

### Information architecture

- Keep one brand/workspace context, one search, Pinned, Recent, Start, School
  setup, Libraries & help and permission-filtered Apps.
- Automatically open Apps and the current application/model on a nested admin
  route. Mark exactly the current destination with `aria-current="page"`.
- Search link text plus app/model aliases, expose a live result count, a clear
  action and an intentional no-results state. Never leave unexplained empty
  headings or inaccessible filtered nodes.
- Pinned and Recent must be genuinely useful: retain query strings, suppress
  only the current page and duplicates, enforce explicit capacity, explain why
  a pin cannot be added, and allow unpin/clear.
- Never show Studio, fleet, Invite School, platform configuration or other
  operator-only controls to a tenant.
- Labels and icons must be real rendered content; no raw Material icon names,
  mojibake, placeholder glyphs or simulated destinations.

### Resilience and accessibility

- Keyboard `/` focuses search only outside editable controls. Arrow/Home/End
  traversal uses the currently visible focus order and handles zero results.
- Connectivity status distinguishes synchronized and offline-ready state. Failed
  writes remain queued locally and sync on reconnection without losing choices.
- Announce meaningful mutations, not every page load. Avoid noisy live regions.
- Compact mode must retain usable navigation and never create a second scroll
  container. Mobile uses the established drawer and one-column page contract.
- Respect reduced motion, light/dark/high-contrast themes and 400% zoom.

## Stage 3 — page-aware layout contract

- Operator workspace grid:
  `minmax(0,1fr) minmax(9.2rem,17%) 2.35rem`.
- Tenant workspace grid:
  `minmax(0,1fr) minmax(9.5rem,18%) 2.35rem`.
- At 1024px and below every workspace is one column.
- Use the entire safe canvas while preserving readable measure. Long forms use
  meaningful field groups, responsive columns and page-aware rails; they must
  not become a thin left strip or an artificial endless blank canvas.
- Keep full native Django tables and compact split Save actions.
- Right rail and tool strip are page-aware. Operator CTAs appear only on the
  operator index. No duplicate shell/header/breadcrumb/nav/drawer/overlay.

## Stage 4 — implementation and release discipline

1. Implement the smallest shared owner that closes every audit ledger row.
2. Add negative-path, permission, cross-host, cross-user, offline, malformed
   payload, capacity, current-route and regression tests.
3. Bump admin build ID, cache-bust ID and service-worker version together when
   CSS/JavaScript changes; update the build lock and monotonicity proof.
4. Update the SOT and autonomous execution log with exact, honest results.
5. If a migration is necessary, create and apply it in the validation database;
   do not invent a migration when an existing JSON preference namespace suffices.

## Primary validation loop

Run, remediate and rerun until green:

- `manage.py check`
- `makemigrations --check --dry-run`
- `migrate --plan`
- `collectstatic --dry-run`
- Django template compilation/structure audit
- repository-wide Python and JavaScript parse gates
- admin preview-parity, leftovers, platform-wide, miss-nothing and emergency
  full-canvas audits
- tenant and operator sidebar verifiers
- shared admin automation verifier and targeted Django tests
- service-worker monotonicity and deployment-artifact checks
- `git diff --check`

On real manager and tenant hosts at 1440/1024/768/390 in light and dark, assert
HTTP 200, correct scope/hostname, one visible H1, no horizontal overflow, no
broken resources, no duplicate CSS URLs, no stylesheet in body, no unexpected
fixed overlays, no raw icon names, native tables, working forms and one sidebar.
Do not substitute `127.0.0.1` evidence for hostname routing.

## Required re-audit loop 1 — adversarial scope and behavior

After the primary loop is green, start a fresh audit from rendered output and
the final tree. Attempt cross-tenant/cross-host preference reuse, unsafe saved
URLs, crafted hidden fields, invalid JSON, oversized lists, offline changes,
duplicate pins, capacity overflow, zero-result keyboard navigation and direct
tenant access to operator destinations. Fix every finding and rerun the primary
gates affected by the fix.

## Required re-audit loop 2 — release and regression independence

Start again from the exact final merged tree. Recompile every template and
script, rerun real-host route/browser evidence, confirm build/cache/SW alignment,
run migration/static/deploy checks, compare every initial ledger row to proof,
and confirm no stale failure artifact claims the repaired behavior still fails.
Any new finding reopens implementation and both affected validation loops.

## Completion and Git

Completion requires every ledger row closed or named as a genuine external
blocker, three green validation passes total (primary + two re-audits), exact
changed-file/test/evidence reporting, and honest deployment steps. Fetch and
reconcile `origin/main`, rerun decisive gates on that merged tree, commit all
in-scope work, push `main`, and verify local HEAD equals `origin/main`.
