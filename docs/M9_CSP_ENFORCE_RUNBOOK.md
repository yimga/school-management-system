# M9 — CSP enforcement (Path A) runbook

**Status: enforce is OFF in production** (`CSP_ENFORCE=0` on all 3 `render.yaml`
services → `Content-Security-Policy-Report-Only`). This runbook is the
ready-to-trigger plan for the two remaining steps. **Both are gated on
capabilities a headless agent does not have** — a browser to verify no CSP
violations fire and that every converted interaction still works, and a **manual
Render deploy** (auto-deploy is OFF). Do STEP 2d, then STEP 3.

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
- **Inline `on*=` handlers:** the recurring/mechanical ones are retired via the
  shared delegated module `static/js/rmc-csp-handlers.js` (loaded from `'self'`):
  - STEP 2a (`938d877ec`): 13 deferred-CSS `onload` → `data-rmc-async-style`.
  - STEP 2b (`12b77579e`): ~35 print/reload + confirm-submit → `data-rmc-print` /
    `-reload` / `data-rmc-confirm` (the last owned by `rmc-modal-intelligence.js`).
  - STEP 2c (`c1075b097`): 23 generic delegations → `data-rmc-submit-on-change` /
    `-select-on-click` / `-select-on-focus` / `-noop-submit`, plus the standalone
    print docs (`reports/term_report`, `reports/annual_report`) and the minimal
    500 page (inline reload → same-URL `<a href="">`).
  - Seal: `apps/security/tests/test_csp_inline_handler_burndown.py` (static-content).

## STEP 2d — the ~40 page-specific inline `on*=` handlers that remain

These call **page-specific** functions (already defined in each page's external
`js/_pages/<app>__<template>.js`, loaded from `'self'`). A nonce cannot authorize
an `on*=` ATTRIBUTE, so each must move to `addEventListener`. **Recipe** (per page,
no new files, no nonce needed):

1. In the template, replace `onclick="fn(arg)"` with a stable hook —
   `data-rmc-action="fn"` and a `data-*` for each argument (many rows already carry
   `data-job-id`, `data-*` etc.).
2. In the SAME page's existing `js/_pages/*.js`, add a delegated binding that reads
   the `data-*` and calls the unchanged function, e.g.:

   ```js
   document.addEventListener('click', function (e) {
     var b = e.target.closest('[data-rmc-action="poll"]');
     if (b) pollJobStatus(b.closest('[data-job-id]').dataset.jobId);
   });
   ```

   (`_pages/evals__import_job_monitor.js` already ends with a `window.addEventListener('load', …)`,
   so the wiring convention is established.)
3. Extend `test_csp_inline_handler_burndown.py`: assert the inline handler is gone
   from the template AND the `_pages/*.js` binds the `data-rmc-action`.
4. **Browser-verify** each page: DevTools console shows no CSP violation, and every
   converted control still fires.

### Inventory (≈20 files, ≈40 handlers)

| Template | Inline handlers | Functions live in |
|---|---|---|
| `evals/import_job_monitor.html` | `refreshJobList` · `toggleJobDetails(this)` · `pollJobStatus(id)` · `exportJobResults(id)` · `retryJob(id)` | `_pages/evals__import_job_monitor.js` |
| `evals/grade_import_upload_v2.html` | `moveToStep3` · `resetUpload`×2 · `applyImport` · `backToValidation` | `_pages/evals__grade_import_upload_v2.js` |
| `evals/compliance_dashboard.html` | `showTeacherDetails(id, '…')` | `_pages/evals__compliance_dashboard.js` |
| `evals/resolve_offline_conflict.html` | inline `getElementById(...)` ×2 | (inline expr → add a named fn) |
| `compliance/dashboard.html` | `muteThreats('…')` ×4 | `_pages/compliance__dashboard.js` |
| `emis/dashboard.html` | `refreshExports()` | `_pages/emis__dashboard.js` |
| `portal/kb_article.html` | `copyUrl()` · `shareOn('…')` ×3 | `_pages/portal__kb_article*.js` |
| `portal/kb_article_submit.html` | `saveDraft()` · inline `getElementById` | `_pages/portal__kb_article_submit.js` |
| `portal/faq_detail.html` | `shareThis()` | `_pages/portal__faq_detail.js` |
| `portal/signature_sign.html` | `clearSignature()` | `_pages/portal__signature_sign.js` |
| `components/announcement_banner.html` | `closeAnnouncement({{id}})` | (shared component script) |
| `components/rmc_bottom_sheet.html` | `RMCSheet.open('…')` · `getElementById` | `RMCSheet` global |
| `components/user_dropdown.html` | `RMCShortcuts.open()` (guarded) | `RMCShortcuts` global |
| `components/pagination.html` | inline URL-building `onchange` | (inline expr → named fn) |
| `academics/ca_marks_input.html` | inline `oninput` expr | (inline expr → named fn) |
| `siteconfig/feature_control_panel_content.html` | `window.open('…')` | (inline → `data-rmc-open-url`?) |
| `siteconfig/partials/reportcard_builder_inner.html` | `window.open('…')` | (inline → `data-rmc-open-url`?) |

### Two special cases — handle explicitly, do NOT blind-convert

- **`schools/super_offboarding_queue.html` — `onclick="event.stopPropagation()"` ×3.**
  Document-level delegation CANNOT reproduce `stopPropagation` (the event has already
  bubbled through the intermediate ancestor by the time it reaches `document`). Fix at
  the ROW handler instead: `if (e.target.closest('a,button,[data-rmc-action]')) return;`
  so clicks on inner controls don't trigger the row.
- **`portal/parent_data_rights.html` (erasure) & `siteconfig/super/marketing_voice_configure.html` (reset)
  — `onclick="return confirm(...)"` on a NAMED submit button in a MULTI-button form.**
  A form-level `data-rmc-confirm` would prompt on the OTHER button too, and the re-submit
  MUST preserve the button's `name=value` submitter (`form.requestSubmit(button)`, not
  `form.submit()`), or the `action=erasure` / `action=reset_marketing_voice` discriminator
  is lost. The erasure path is **destructive ("cannot be undone")** — verify the confirm
  gate still fires on exactly that button before shipping.

## STEP 3 — flip enforce (hard-to-reverse; confirm with the operator first)

0. **Re-audit** on the tip you will deploy: zero inline `on*=` outside `templates/admin/**`
   and zero un-nonced executable inline `<script>` (non-`src`, non-`application/json`).
1. Set `CSP_ENFORCE=1` on all three services in `render.yaml` (web + the 2 workers/
   services that render HTML). This emits `Content-Security-Policy` (enforcing) instead
   of `-Report-Only`.
2. **Manual Render deploy** — auto-deploy is OFF, so a merge alone does nothing.
3. **Browser validation** (before calling it done): on tenant portal, manager/control
   plane, and marketing surfaces — open DevTools, confirm NO `Content-Security-Policy`
   violation reports, and exercise: print buttons, filter `<select>`s (auto-submit),
   copy-token inputs, the confirm sheets, import-monitor controls, KB share/copy.
4. **Rollback** = set `CSP_ENFORCE=0` + redeploy (instant revert to Report-Only).

## Monitoring while still Report-Only

`CSP_REPORT_URI` (default `/security/csp-report/`) already collects violation reports.
Watch it for a clean window before STEP 3 — real violations there are the pages STEP 2d
still needs to cover.
