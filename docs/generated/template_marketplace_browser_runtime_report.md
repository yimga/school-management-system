# Template Marketplace Browser Runtime Report (Batch 1506)

## Specs

- `tests/e2e/template-marketplace.spec.js` (existing batch 1401)
- `tests/e2e/template-marketplace-runtime.spec.js` (NEW batch 1506)

## Browser run

**Not executed in this batch.** Browser execution requires:

- Provisioned tenant
- Running web server
- Playwright runner

The specs are committed and ready to run when those preconditions land.

## Contract assertions (specs cover)

- Marketplace browse route loads with ≥1 template card
- Preview returns 200 + no console errors
- Apply requires POST + CSRF (GET never auto-applies)
- Operator-only template returns 404 in tenant scope
- No horizontal overflow at 390×844 mobile viewport

## Repo-scope fallback runtime tests (PASS)

| Module | Tests |
| --- | ---: |
| `test_template_marketplace_runtime` | 5 |
| `test_template_preview_apply_rollback_runtime` | 4 |
| `test_template_tenant_boundary_runtime` | 4 |
| `test_tenant_studio_template_selection_runtime` | 4 |
| `test_studio_os_template_integration_runtime` | 5 |
| **Total** | **22** |

**Verdict:** TEMPLATE MARKETPLACE BROWSER RUNTIME — SPECS READY; BROWSER EXECUTION PENDING LANE 2.
