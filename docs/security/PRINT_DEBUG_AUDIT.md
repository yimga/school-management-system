# Print and debug leakage audit

**Goal:** Replace `print()` with structured logging in application and worker paths; remove or isolate debug prints from user-facing and production code.

## Policy

- **Application/worker code (apps/, config/):** Use `logging.getLogger(__name__).info/debug/warning` (or project logger); no `print()` in request/response or task paths.
- **Management commands:** `self.stdout.write()` for user output; `logging` for diagnostics. Avoid raw `print()` unless script is dev-only and documented.
- **Tests:** `print()` in tests is acceptable for local debugging but should not run in CI as part of assertions; prefer capsys or logging capture.

## Inventory (apps/ — application and worker paths)

Files under `apps/` that contain `print(` (sample; run `grep -rn "print\s*(" apps/ --include="*.py"` for full list):

| File | Count | Path type | Action |
|------|-------|-----------|--------|
| apps/siteconfig/ai_assistants.py | 1 | Application | Replace with logger. |
| apps/siteconfig/education_profile_engine.py | 1 | Application | Replace with logger. |
| apps/siteconfig/url_structure.py | 1 | Application | Replace with logger. |
| apps/platform_runtime/runtime_resolver.py | 2 | Application | Replace with logger. |
| apps/policies/resolver.py | 2 | Application | Replace with logger. |
| apps/policies/resolvers.py | 1 | Application | Replace with logger. |
| apps/policies/registry.py | 5 | Application | Replace with logger. |
| apps/policies/blueprint_registry.py | 3 | Application | Replace with logger. |
| apps/policies/models.py | 1 | Application | Replace with logger. |
| apps/finance/payment_processors.py | 1 | Application | Replace with logger. |
| apps/schools/super_views.py | 2 | Request path | Replace with logger. |
| apps/marketplace/views.py | 1 | Request path | Replace with logger. |
| apps/portal/runtime_helpers.py | 1 | Application | Replace with logger. |
| apps/siteconfig/management/commands/seed_admin_dashboard_palettes.py | 1 | Mgmt command | Prefer self.stdout.write or logger. |
| apps/siteconfig/tests/*.py | 4 | Test | Prefer capsys or remove. |
| apps/marketplace/tests/*.py | 1 | Test | Prefer capsys or remove. |
| apps/finance/tests/*.py | 1 | Test | Prefer capsys or remove. |

## Next steps

1. **Replace in request/worker path:** For each non-test file above, replace `print(...)` with `logger = logging.getLogger(__name__); logger.debug(...)` (or appropriate level). Ensure no PII or secrets in log messages.
2. **Management commands:** Audit all `management/commands/*.py` for `print(`; use `self.stdout.write()` for user-facing output and logging for diagnostics.
3. **CI/lint:** Add a check (e.g. script or pre-commit) that fails if `print(` appears in `apps/**/*.py` outside `tests/` or `management/commands/` (with allowlist if needed).
4. **Root and config:** Run same audit for `config/`, root-level scripts, and worker entrypoints; separate dev-only scripts from production code.
