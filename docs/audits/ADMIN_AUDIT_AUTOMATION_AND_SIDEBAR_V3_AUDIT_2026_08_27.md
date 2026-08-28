# Admin audit automation and sidebar v3 audit

Date: 2026-08-27  
Status: implemented and validated. The approval boundary below authorised the v3
contracts; the sidebar, the preference service, the destination registry and the
fail-closed evidence verifier are now in the tree. What is NOT yet satisfied is
loop 2: no real-host browser sweep has produced v3 evidence, so
`scripts/verify_admin_playwright_sweep_audit.py` fails closed by design until
`bash scripts/run_admin_abrupt_end_sweep.sh` runs with `SWEEP_INCLUDE_TENANT=1`.
That failure is the honest state, and it replaces a committed render-contract
PROXY artifact that had been satisfying the same gate with no browser involved.  
Scope: tenant and operator Django `/admin/` surfaces, with the tenant sidebar as the first behavioral implementation target

## Executive finding

The current sidebar is a useful v2 foundation, but its state synchronization and its proof system are not production-grade. The strongest risk is not visual: simultaneous browser tabs and stale offline state can overwrite newer server state. The strongest audit risk is that a render-contract proxy can satisfy a gate named as a Playwright sweep even when no tenant browser behavior was exercised.

The proposed v3 keeps the current admin shell and upgrades the sidebar into a permission-aware, page-aware task navigator backed by revisioned, conflict-safe preferences. Audit automation is split into independently verifiable source, server, browser, accessibility and evidence-freshness layers.

## Root-cause ledger

| Priority | Area | Current behavior | Root cause | Required upgrade | Release proof |
|---|---|---|---|---|---|
| P0 | Preference correctness | Rapid full-state saves can complete out of order and replace a newer state | No revision, compare-and-swap, mutation queue or idempotency key | Revisioned PATCH operations, serialized/coalesced client queue and HTTP 409 rebase | Two-tab and reordered-response integration tests |
| P0 | Offline recovery | A stored whole-state snapshot wins over the server on load | Pending state has no base revision or operation log | Store semantic operations, fetch latest revision, rebase, then retry with bounded backoff | Offline-to-online Playwright scenario |
| P0 | Audit truth | Render-contract proxy evidence can pass the Playwright audit verifier | Proxy and browser artifacts share one contract and permissive default verification | Separate immutable render and browser evidence; browser gate requires browser provenance | Strict verifier rejects proxy, stale SHA and missing tenant host |
| P0 | CI coverage | Admin browser job excludes tenant routes | `SWEEP_INCLUDE_TENANT=0` and incomplete workflow path filters | Mandatory operator and tenant hostname matrix; include sidebar JS, CSS, service, tests and cache IDs in triggers | CI artifact contains both site types and route digest |
| P1 | Preference storage | Navigation shares a JSON document with writers that do not all lock or merge | No common atomic namespace service | Dedicated preference record or one atomic namespaced update service | Concurrency test across navigation, dashboard and form preferences |
| P1 | Navigation identity | Pins are stored primarily as raw paths | No canonical destination registry | Stable destination IDs resolved and permission-checked server-side; path is display fallback only | Removed/renamed/unauthorized destination tests |
| P1 | Sidebar semantics | Advanced navigation uses a heading with button behavior; templates contain inline state/style logic | Behavior and presentation are spread across templates | Native buttons, declarative data contract and maintained CSS modules | HTML semantics and CSP-compatible static scan |
| P1 | Compact mode | Compact mostly hides content rather than becoming a useful navigation mode | No explicit rail information architecture | True 72px icon rail with tooltips/flyouts; 288-304px expanded sidebar; off-canvas mobile drawer | 1440/1024/768/390 and 400% zoom screenshots |
| P1 | Internationalization | Client status and action strings are hardcoded | No translated string contract | Server-provided localized strings with safe fallbacks | Language-switch browser test |
| P2 | Findability | Search is substring filtering over existing links | No semantic registry, ranking or action model | Weighted command search across destinations, records and permitted actions | Keyboard and zero-result behavioral tests |
| P2 | Recovery UX | Pin/unpin/clear is immediate with no undo or conflict explanation | Minimal optimistic UI | Undo toast, conflict resolution message and non-destructive reset | Error-state and keyboard tests |
| P2 | Observability | Save failures collapse into a generic offline message | No typed error or telemetry contract | Typed failure states and aggregate latency/conflict/retry telemetry without PII | Telemetry schema and failure injection tests |

## Sidebar v3 information architecture

1. Workspace: school/operator identity, effective role and synchronization state.
2. Command search: permission-filtered destinations, records and actions with keyboard navigation.
3. Now: at most three genuine, actionable items; no duplicate dashboard vanity metrics.
4. This page: current app/model context and only the permitted list/add/history actions relevant to the page archetype.
5. Pinned: stable semantic destinations, keyboard reorder, capacity feedback and undo.
6. Work areas: page-aware domain clusters. The current cluster opens; unrelated clusters remain compact.
7. All Django models: complete native catalog kept available but deliberately secondary.

Operator and tenant registries must remain separate. Tenant state cannot expose Studio, fleet, invite-school or operator-only destinations. Operator index CTAs remain index-only.

## Preference v3 contract

Each scope is keyed by normalized hostname, admin-site identity, user and mode. It contains:

- `schema_version`
- monotonic `revision`
- `updated_at`
- ordered stable destination IDs
- compact/density and expansion preferences
- last acknowledged mutation ID

The client sends semantic operations such as `pin`, `unpin`, `move`, `set_mode` and `clear_recent`, not an unqualified replacement document. The server validates permissions and the expected revision inside one transaction. A mismatch returns 409 with the current safe state. Offline storage contains the operation queue and its base revision, never a whole snapshot that silently outranks the server.

## Audit automation v3 contract

The following evidence is separate and mandatory:

1. Source/static: template compilation, CSS ownership, duplicate URLs, malformed glyphs, native controls and cache-ID synchronization.
2. Server: Django tests, tenant scoping, route permissions, optimistic concurrency, namespace atomicity and invalid-input handling.
3. Browser: real operator and tenant hostnames, genuine clicks and form/navigation actions, reload, two tabs, offline recovery and resource health.
4. Accessibility/visual: keyboard, focus, 400% zoom, reduced motion, light/dark/high contrast and automated accessibility scan.
5. Evidence seal: git SHA, build/cache/service-worker IDs, route-manifest hash, host matrix, browser versions, viewport/theme matrix, timestamp and expiry.

A render-contract crawler cannot write or satisfy browser evidence. Generator commands require an explicit `--write`; verifiers are read-only. Stale, overwritten, proxy or source-mismatched evidence fails closed.

## Three post-implementation loops

### Loop 1: source and server

Run Django checks, migrations checks, template compilation, unit/integration tests, route/scoping assertions, static/resource ownership and diff checks.

### Loop 2: real-host behavior

Run operator and tenant browser matrices at 1440, 1024, 768 and 390 pixels in light and dark themes. Exercise search, pin, unpin, reorder, undo, compact mode, mobile drawer, current-area expansion, reload and permissions.

### Loop 3: adversarial and evidence integrity

Run overlapping tab writes, reordered responses, offline mutation rebase, expired session, revoked permission, deleted destination, localization, 400% zoom and stale/tampered evidence checks.

## v3.1 serious-upgrade additions

The first approval review identified six further improvements that strengthen the architecture without turning the sidebar into a dashboard:

1. **Explicit context lens.** The destination registry is evaluated against a typed context containing admin site, hostname scope, tenant, effective role, permissions and page archetype. Tenant and operator navigation are not branches of a client-side label list; they are separate server-resolved result sets.
2. **Page-archetype composition.** Index, app index, changelist, add, change, history, delete, delete-selected and guided-action surfaces expose different `This page` actions. The sidebar consumes a semantic page contract rather than guessing from URL strings.
3. **Command palette contract.** Search results are grouped as destinations, records and actions. Scoring combines exact aliases, current work area, recency and permission-safe frequency. Results carry stable IDs, descriptions and scope badges. Empty, loading, partial and unavailable states are first-class.
4. **Explainable recommendations.** `Now` items include a server reason code, source timestamp and destination. The interface can answer why an item is recommended and dismiss or snooze optional recommendations. Mandatory compliance tasks cannot be silently hidden.
5. **Focus mode.** A reversible per-user mode suppresses ambient recommendations and pins while retaining the current page, core work areas and search. It never changes permissions or server state beyond its own preference.
6. **Evidence replay.** Every browser evidence row includes a scenario ID, trace ID, host, starting revision, mutations, ending revision, screenshots and resource log. A verifier can replay the scenario against the sealed build and compare the outcome digest.

### Typed server contracts

The implementation should introduce immutable Python value objects or typed dictionaries for:

- `AdminNavigationContext`
- `AdminDestination`
- `AdminPageContract`
- `AdminRecommendation`
- `NavigationMutation`
- `NavigationConflict`
- `BrowserEvidenceManifest`

Registry generation, preference mutation, recommendation calculation and evidence verification remain separate services. Templates receive serialized display contracts and never reconstruct permission or tenant-scoping decisions.

### Failure-state requirements

- If recommendation calculation fails, core navigation remains usable and the failure is logged with a trace ID.
- If preference persistence fails, the UI retains the user's pending operation, identifies the failure type and offers a safe retry.
- If a destination becomes unauthorized or cannot be reversed, it is removed from rendered results and preserved only as diagnostic metadata.
- If command search is unavailable, the native work-area and Django model navigation remains complete.
- If browser evidence is stale or incomplete, release verification fails; it never silently downgrades to proxy evidence.

## Approval boundary

The companion HTML is a visual and behavioral proposal. Approval authorizes implementation of the v3 contracts across tenant and operator admin foundations, followed by the three validation loops. It does not authorize replacing native Django tables or adding simulated controls.
