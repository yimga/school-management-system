# Tenant Django admin sidebar and automation audit — 2026-08-20

## Scope

Two-pass source/runtime audit of the tenant and operator Django admin site
classes, shared templates, sidebar partials, preference ownership, static assets,
host routing and existing verification. The approved full-canvas owner remains
in force; this audit focuses on navigation behavior and regression boundaries.

## Initial audit ledger

| Surface | Root cause | Resolution | Proof owner |
| --- | --- | --- | --- |
| Tenant pinned pages | `runmycampus-admin-pinned` was browser-global and owned by an inline base template script | Move to validated `DashboardUserPreference.dashboard_layout` namespace scoped by user + host + admin site; local storage is scoped retry only | navigation service tests + sidebar verifier |
| Tenant recent pages | `rmc-tenant-admin-recent-v2` was browser-global | Same server namespace and opaque local scope | cross-host isolation test |
| Tenant recent usefulness | Renderer removed any recent page already present in canonical navigation | Suppress only duplicate entries and the current page | runtime source/DOM test |
| Compact/advanced state | Shared global local-storage keys could cross tenants | Server-owned scoped booleans, queued offline | endpoint round-trip test |
| Current app | outer Apps accordion always initialized closed despite the template comment | Open for nested current routes and preserve scoped preference | template contract test |
| Search | model aliases were emitted only for the embedded operator catalog; no intentional empty/reset state | Emit aliases on tenant links, live count, clear and no-results state | sidebar verifier |
| Pin limits | duplicate/full operations failed silently | disabled already-pinned state plus explicit accessible capacity feedback | JS/parser + source test |
| Icon encoding | emoji/symbol content introduced an avoidable encoding risk | use inline SVG with text alternatives/hidden decoration | template structure audit |
| Preference endpoint | no admin navigation endpoint existed | add `AdminSite.admin_view`-wrapped GET/POST endpoint with bounded JSON, same-host `/admin/` path allowlist and atomic write | endpoint negative-path tests |
| Operator boundary | shared base script also attempted to own navigation state | remove legacy base owner; leave established operator sidebar/runtime intact | operator sidebar verifier |

## Standards applied

- Django `AdminSite.each_context()` for shared per-page admin context.
- Django `AdminSite.admin_view()` for authenticated staff-only custom admin URLs.
- Side-effect-free GET and CSRF-protected POST for preference mutation.
- WAI `aria-current="page"` for current location and live status only for
  meaningful search/mutation feedback.

## Implemented release state

- The tenant sidebar is now a single server-backed navigation owner. Pinned,
  recent, compact, Advanced and Apps state is isolated by authenticated user,
  exact hostname and admin-site name. Browser storage contains only a scoped
  offline retry envelope.
- The endpoint is protected by `AdminSite.admin_view`, accepts CSRF-protected
  POST only for mutation, bounds payload/path/label/cardinality values, permits
  relative same-admin paths only and fails closed on malformed input.
- Tenant navigation has alias-aware search, a live result count, an explicit
  reset, a useful no-results state, keyboard-safe zero-result behavior, current
  route expansion, recent pages and accessible pin-capacity feedback.
- A pinned shortcut replaces its canonical visible counterpart, so pinning
  cannot create duplicate visible navigation. Operator navigation remains
  separately owned and tenant-only assets do not mount there.
- The full admin registration audit remains clean: 474 registrations (197
  operator, 277 tenant), zero findings and zero tenant school selectors.
- The exhaustive manager-host changelist crawl found two genuine 403 routes.
  `TenantIntegrationAdminMixin` had been reused on `PlatformAdminSite` and
  rejected requests without `request.school`. It now delegates to ordinary
  Django model permissions on the operator site while preserving tenant owner
  checks and tenant delete denial. Final result: 189 HTTP 200 routes and two
  intentional redirect escapes across 191 routes, with zero failures.

## Browser and computed-style proof

The manager and Gilead tenant hostnames were exercised independently using real
host routing. The matrix covered 1440, 1024, 768 and 390 pixels in light and
dark modes. All scoped samples returned HTTP 200 with the correct host/site,
one visible H1, no horizontal overflow, no broken resource, no duplicated CSS
URL, no stylesheet in `body`, no unexpected fixed overlay and no raw icon name.
The measured 1440 grids were:

- operator: `840.812px 207.594px 37.5938px`
- tenant: `805.75px 188.625px 37.5938px`

Both satisfy the approved `minmax(0, 1fr)` plus percentage rail and 2.35rem tool
strip contracts. At 1024 and below both resolved to a single content column.

## Two independent post-implementation loops

### Re-audit loop 1 - adversarial scope and ownership

- Re-crawled all 191 manager admin changelist routes and closed the two
  integration permission failures described above.
- Seeded a canonical tenant user-list pin at 390px dark mode and proved one
  visible destination, not a pinned/canonical duplicate.
- Re-ran preview-shell, manager layout, theme isolation, interaction integrity,
  tenant sidebar and operator boundary gates. Stale assertions that demanded a
  retired permanent live strip, global copilot or old civic footer were updated
  to enforce the approved quiet header, drawer-owned activity and page-aware
  admin footer rather than obsolete markup.

### Re-audit loop 2 - independent release seal

- `manage.py check`, migration drift, migration plan, collectstatic dry-run,
  template compilation, preview parity, canvas contract, miss-nothing,
  emergency audit, form intelligence, both sidebar gates, footer contract and
  service-worker monotonicity passed.
- Fifteen focused assertions passed: ten Django sidebar/operator/integration
  tests plus five transactional database-backed navigation-preference tests.
- Emergency coverage passed across 474 models, 91 templates, 326 stylesheets and
  28 browser surfaces, with one terminal layout owner and zero findings.
- Build/cache/service-worker ownership is synchronized at
  `2026-08-20-v22.0`, `20260820-tenant-admin-sidebar-v22` and
  `sms-v4.06.71-tenant-admin-sidebar-server-preferences-2026-08-20`.

No schema change was introduced by this slice. The migration plan reports the
pre-existing `schoolops.0039_procurement` and `0040_procurement_rls`; deployment
must apply them if the target database still reports them.

## Honest boundary

Repository and real-host browser evidence can prove generated markup, routing,
behavior and static ownership. Production only changes after migrate/static
collection/process restart/cache invalidation; repository completion alone is
not a deployment claim.
