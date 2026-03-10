# Subprocess usage safety audit

All subprocess usage must be reviewed for: shell injection risk, shell=True, path sanitization, timeouts, low-privilege execution, and logging.

| File | Function/context | Purpose | shell= | Timeout | Input sanitized? | Verdict |
|------|------------------|---------|-------|---------|------------------|---------|
| apps/siteconfig/management/commands/sync_regional_models.py | L21 | Sync (external cmd) | No | Yes (L28) | Review | Keep, document |
| apps/siteconfig/tests/test_theme_studio.py | L491 | Test | No | Review | Test input | Keep |
| apps/finance/receipt_verification.py | L166 | Receipt verification (e.g. tesseract) | No | Review | User-derived path? | Sanitize paths, add timeout |
| scripts/dev/capture_backend_screenshot.py | L73 | Dev screenshot | No | Review | Dev only | Keep |
| scripts/reset_local_db.py | L33 | DB reset | Review | No | Script | Add timeout |
| scripts/gen_models_png.py | L25 | Diagram gen | No | Yes (L44) | Review | Keep |
| scripts/run_sweep_ab.py | L30 | Sweep | No | Review | Review | Keep |
| apps/siteconfig/management/commands/generate_models_diagram.py | L32 | Diagram | No | Yes (L51) | Review | Keep |
| apps/platform_runtime/tests/test_tenant_settings_lint.py | L21, L40 | Tests | No | Review | Test | Keep |
| apps/portal/document_conversion.py | L85 | Document conversion | No | Review | User input? | Sanitize, timeout |
| apps/portal/document_generation.py | L61 | Doc generation | No | 90s | Review | Keep |

**Actions:** Ensure no shell=True with user input; add timeouts where missing; sanitize file/path inputs in receipt_verification and document_conversion; log failures.

**Remediation done:** reset_local_db.py — subprocess.run with timeout=300; receipt_verification.py — timeout=25, logging on failure and TimeoutExpired; document_conversion.py — timeout=120, logging on failure; docstring notes user-derived path safety. See UX_PLAN_FULL_COMPLETION_REGISTER.

## Required remediation (non-negotiable)

These must be completed; no deferral to backlog. Track in [UX_PLAN_FULL_COMPLETION_REGISTER.md](../plan/UX_PLAN_FULL_COMPLETION_REGISTER.md).

1. **sync_regional_models.py** — Document timeout and input source; keep.
2. **receipt_verification.py** — Sanitize any user-derived paths; add timeout; log failures.
3. **reset_local_db.py** — Add timeout; document as dev-only.
4. **document_conversion.py (portal)** — Sanitize user input paths; add timeout; log failures.
5. **All subprocess call sites** — Confirm no shell=True with user input; add timeouts where missing; log failures. Re-audit after changes.
