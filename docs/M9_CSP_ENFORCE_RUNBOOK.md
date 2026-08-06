# M9 — CSP enforcement (Path A) runbook

**Status: enforce is OFF in production** (`CSP_ENFORCE=0` on all 3 `render.yaml`
services → `Content-Security-Policy-Report-Only`). **The code burndown is
COMPLETE** — STEP 2d landed (`3e2885883`, 2026-08-06): the served (non-admin)
inline-`on*=` surface is at **ZERO**, sealed by the zero-tolerance gate
`scripts/scan_inline_event_handlers.py`. Only **STEP 3** remains, and it is gated
on capabilities a headless agent does not have — a browser to confirm no CSP
violations fire and that every converted interaction still works, plus a **manual
Render deploy** (auto-deploy is OFF).

## Posture (settled — do not relitigate)

Path A = strict `script-src`, pragmatic `style-src`:

```
script-src 'self' 'nonce-<per-request>'   ← NO 'unsafe-inline' / 'unsafe-eval' (the XSS-meaningful directive)
style-src  'self' 'unsafe-inline'          ← ~2,300 inline style="…" attrs; a nonce can't authorize a style ATTRIBUTE
```

- **CSP3 trap:** a directive carrying BOTH a nonce AND `'unsafe-inline'` makes
  browsers IGNORE `'unsafe-inline'`. So the nonce is added to **`script-src` only**
  (`apps/security/csp_middleware.py::_build_policy`). Never add it to `style-src`.
- Middleware **bypasses** `/admin/`, `/static/`, `/media/` — Django admin (Unfold
  Alpine.js needs `eval`) and static assets keep default behavior. All
  `templates/admin/**` inline handlers/scripts are therefore **out of scope**.

## What is already enforce-ready

- **Style axis:** done — `style-src` carries `'unsafe-inline'`; the ~2,300 inline
  style attributes are accepted by design.
- **Inline `<script>` blocks:** effectively done. Executable inline scripts across
  the platform are already nonced (`nonce="{{ csp_nonce }}"`, 147+ blocks) and the
  Category-C pages keep their JS in external `js/_pages/*.js` files loaded from
  `'self'` plus `type="application/json"` data blocks — all CSP-clean. Regression
  gate: `verify_csp_nonce_emission.py` (baseline 0). **Re-scan before flipping**
  (see STEP 3.0) to confirm no new un-nonced inline script slipped in.
- **Inline `on*=` handlers:** DONE — retired via the shared delegated module
  `static/js/rmc-csp-handlers.js` (loaded from `'self'`) + per-page `_pages/*.js`:
  - STEP 2a (`938d877ec`): 13 deferred-CSS `onload` → `data-rmc-async-style`.
  - STEP 2b (`12b77579e`): ~35 print/reload + confirm-submit → `data-rmc-print` /
    `-reload` / `data-rmc-confirm` (the last owned by `rmc-modal-intelligence.js`).
  - STEP 2c (`c1075b097`): 23 generic delegations → `data-rmc-submit-on-change` /
    `-select-on-click` / `-select-on-focus` / `-noop-submit`, plus the standalone
    print docs (`reports/term_report`, `reports/annual_report`) and the minimal
    500 page (inline reload → same-URL `<a href="">`).
  - STEP 2d (`3e2885883`): the final **40 page-specific handlers across 21
    templates** (+1 JS-generated). Generic patterns → the module's new
    `data-rmc-stop-propagation` / `-popup` / `-click-target` / `-navigate-param` /
    `-set-and-submit` / `-open-shortcuts` / `-derive-name`; bespoke functions →
    `addEventListener` inside each page's own `_pages/*.js`; confirms → button-
    level `data-rmc-confirm`.
  - Seal: `scripts/scan_inline_event_handlers.py` (baseline 0, zero-tolerance;
    wired into `architectural-boundaries.yml` + `pre_push_boundary_check.py` +
    `verify_ci_gate_wiring` REQUIRED_GATES; 9 unit tests) **plus**
    `apps/security/tests/test_csp_inline_handler_burndown.py` (static-content,
    Batch2 + module-capability + scanner=0).

## STEP 2d — DONE (`3e2885883`, 2026-08-06)

All 40 page-specific inline `on*=` handlers across 21 templates (plus one
JS-generated `onclick` in `_pages/portal__kb_article_submit.js`) are retired.
`scan_inline_event_handlers.py` now fails CI + the local pre-push hook on any
reintroduction. Nothing re-hosts `eval`; no new inline `<script>` was added —
bespoke functions bind via `addEventListener` in each page's existing external
`_pages/*.js`, generic patterns via `data-rmc-*` markers on the shared
`rmc-csp-handlers.js`.

How the two special cases were actually solved (refining this runbook's earlier
sketches):

- **`schools/super_offboarding_queue.html` stop-propagation ×3** → new
  `data-rmc-stop-propagation`, bound as a **direct target-phase** listener (NOT
  document delegation, which the event has already bubbled past). This preserves
  the exact inline `event.stopPropagation()` timing and coexists with the
  same-element `data-rmc-approve-request` / `-reject-request` handlers (it stops
  the bubble to the clickable row, not sibling listeners on the same element).
- **`parent_data_rights` (erasure) & `marketing_voice_configure` (reset) named
  submit buttons** → **button-level** `data-rmc-confirm`. `rmc-modal-intelligence.js`
  re-dispatches an OK'd click via `el.click()` on the actual submit button, so the
  `name=value` submitter (`action=erasure` / `action=reset_marketing_voice`) is
  preserved and only that button prompts. The destructive erasure gate was
  verified to still fire on exactly that button.

Repaired while auditing: `emis` `loadRecentExports` now returns its promise (the
old `refreshExports().finally` threw on `undefined`); `compliance_dashboard_view`
emits `deadlines_json` (valid JSON, not the Python repr the inline literal passed).
Several bespoke functions (`muteThreats` / `showTeacherDetails` / `refreshExports`)
were already dead `ReferenceError`s — IIFE-trapped by the earlier `_pages`
extraction — and the rebind repaired them.

## STEP 3 — flip enforce (hard-to-reverse; confirm with the operator first)

0. **Re-audit** on the tip you will deploy: `python scripts/scan_inline_event_handlers.py`
   reports **0** (zero inline `on*=` outside `templates/admin/**`), and
   `verify_csp_nonce_emission.py --compare` is clean (no un-nonced executable
   inline `<script>`, non-`src`, non-`application/json`).
1. Set `CSP_ENFORCE=1` on all three services in `render.yaml` (web + the 2 workers/
   services that render HTML). This emits `Content-Security-Policy` (enforcing) instead
   of `-Report-Only`.
2. **Manual Render deploy** — auto-deploy is OFF, so a merge alone does nothing.
3. **Browser validation** (before calling it done): on tenant portal, manager/control
   plane, and marketing surfaces — open DevTools, confirm NO `Content-Security-Policy`
   violation reports, and exercise: print buttons, filter `<select>`s (auto-submit),
   the page-size navigator, copy-token inputs, the confirm sheets (incl. the erasure
   gate), import-monitor controls, KB share/copy, the announcement close, the
   keyboard-shortcuts dropdown item.
4. **Rollback** = set `CSP_ENFORCE=0` + redeploy (instant revert to Report-Only).

## Monitoring while still Report-Only

`CSP_REPORT_URI` (default `/security/csp-report/`) already collects violation reports.
Watch it for a clean window (7+ days for production) before STEP 3 — real violations
there are the only remaining signal now that the static inline-`on*=` surface is 0.
