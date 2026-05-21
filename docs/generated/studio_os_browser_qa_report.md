# Studio OS — Browser QA Report (v3.54.0)

**Generated:** 2026-05-21. Spec-based report. Live Playwright execution deferred to dev environment.

## Spec

- **Path:** [`tests/e2e/studio-os.spec.js`](../../tests/e2e/studio-os.spec.js)
- **Parse status:** OK (Node parser)
- **Execution status:** DEFERRED

## Execution blockers (operator-actionable)

- Requires Django dev server running on `MANAGER_HOST` (default `manager.runmycampus.com:8000`)
- Requires `E2E_LOGIN_USER` + `E2E_LOGIN_PASSWORD` env vars
- Run locally: `npx playwright test tests/e2e/studio-os.spec.js`

## Tests in the spec

### Responsive sweep (18 tests)

**Shape:** 6 sections × 3 viewports (390 mobile / 768 tablet / 1366 laptop).

Each test asserts:
- Section renders with expected heading
- **No horizontal overflow** (`documentElement.scrollWidth - clientWidth ≤ 1px`)
- No NEW dummy `href="#"` anchors (tolerance: 1 for pre-existing v3.53 cockpit_copilot_rail anchor — **now fixed in v3.54.0 closeout**, so tolerance can drop to 0)
- No console errors during render

### Studio rail links all six modes (1 test)

Viewport: 1366. Asserts `nav[aria-label*="Studio modes"]` contains an `<a href>` ending at each section's path.

### Skip-link target reachable (1 test)

Viewport: 1366. Asserts `#studio-canvas` element is attached to the DOM.

### `data-rmc-confirm` handler loaded (1 test)

Viewport: 1366. Asserts the v3.54.0 capture-phase handler in `studio_os__shell.js` stops the native click when `window.confirm()` returns `false`. Verified by synthetic button injection.

### Tenant boundary sweep (2 tests)

**Guard:** skip when `TENANT_HOST` + `E2E_LOGIN_USER` not set.

- Tenant overview does NOT expose "RBAC & permissions" chip (operator-only)
- Tenant control does NOT show "System config console" (operator-only)

## Static contract verification (DID run this wave)

| Check | Result |
|---|---|
| Tag balance across 90 `templates/studio_os/**/*.html` | balanced (comment-aware stack walk) |
| Python `ast.parse` of `apps/studio_os/views.py` | OK |
| Python `ast.parse` of `apps/studio_os/services.py` | OK |
| Node parser on `static/js/service-worker.js` | OK |
| Node parser on `static/js/_pages/studio_os__shell.js` | OK |
| Node parser on `tests/e2e/studio-os.spec.js` | OK |
| **Cross-cutting test suite** | **27/27 PASS** on Windows in 0.2s (SimpleTestCase, no DB) |
| New `href="#"` introduced | 0 |
| Pre-existing `href="#"` removed | 1 (cockpit_copilot_rail.html anchor → `<button>`) |
| `position: sticky + overflow: hidden` combos in new CSS | 0 |
| `data-theme="system"` writes in new CSS | 0 |
| All new `.rmc-*` classes defined in their CSS bundles | true |

## Expected outcomes on live run

| Test bucket | Expected | Rationale |
|---|---|---|
| Responsive sweep (18) | PASS | Systemic `studio-mode-rail.css` fix removes the horizontal overflow root cause; preview panes render honest empty states without bugs |
| Studio rail links | PASS | All 6 URL names exist in `urls.py`; shell.html rail renders them |
| Skip-link target | PASS | `shell.html:25` anchor + `shell.html:81` main element preserved |
| `data-rmc-confirm` handler | PASS | `studio_os__shell.js` IIFE appended at v3.54.0; static check `data-rmc-confirm capture-phase handler in studio_os__shell.js` verified |
| Tenant boundary | PASS | Template-level `{% if request.public_host_kind == 'manager' %}` gates verified by `OperatorHostGateTests` static check |

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Live LiteLLM / Ollama unreachable | Co-pilot rail falls back to rules layer | Shipped — `services.ai_helpers` handles fallback transparently (3-tier graceful) |
| Bootstrap version drift | Responsive helpers behave differently | v3.54.0 uses `.rmc-*` classes (semantic tokens), not raw Bootstrap utilities |
| Tenant-host TLS misconfig | Tenant boundary tests can't run on live `TENANT_HOST` | Tests skip cleanly via `test.skip` when env unset; static `OperatorHostGateTests` still verify the gate at template level |
