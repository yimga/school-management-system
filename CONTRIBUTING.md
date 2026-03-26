# Contributing to RunMyCampus

Thank you for contributing. This document covers **non-negotiable** standards for UI and security so the product stays outcome-first, role-native, and secure.

## New and changed pages (required)

**Every new or heavily changed page must:**

1. **Conform to a page archetype** — Role Home, Setup Studio, Decision Console, Operational Workbench, or Catalog/Marketplace. See [docs/ui/PAGE_ARCHETYPES.md](docs/ui/PAGE_ARCHETYPES.md).
2. **Pass the 5-question test:**
   - What problem does this page solve?
   - What matters most right now?
   - What is the primary next action?
   - What can I do in one click?
   - What should I not have to click for?
3. Use outcome-first language (user goals, not module names).
4. Use shared design tokens and [static/css/platform-high-end.css](static/css/platform-high-end.css) where applicable (cards, CTAs, empty states).

**Checklist for PRs that add or refactor pages:** Document in the PR that the page maps to an archetype, passes the 5-question test, and uses the shared visual system. No new page may ship without this.

Reference: [docs/ui/PAGE_ARCHETYPES.md](docs/ui/PAGE_ARCHETYPES.md), [docs/ui/OPERATIONAL_WORKBENCH.md](docs/ui/OPERATIONAL_WORKBENCH.md).

## Security and runtime

- **Secrets:** Do not commit `.env`, `.env.local`, or any file with real API keys or passwords. Use `.env.example` with placeholders. See [SECURITY.md](SECURITY.md) if present.
- **Tenant-facing logic:** Do not use `SiteSettings` / `get_solo` directly in tenant-facing flows; use runtime resolvers. See [docs/security/SITESETTINGS_INVENTORY.md](docs/security/SITESETTINGS_INVENTORY.md).
- **Logging:** Use `logging.getLogger(__name__)` in application/worker code; do not use `print()` in request or task paths. See [docs/security/PRINT_DEBUG_AUDIT.md](docs/security/PRINT_DEBUG_AUDIT.md).
- **Host/domain:** Prefer [apps/schools/domain_resolution_service.py](apps/schools/domain_resolution_service.py) for base host, tenant URL, and env-specific routing instead of scattering `request.get_host()` or hardcoded domains.

## Pre-merge verification (recommended)

Before opening a PR (or after large template/i18n changes):

1. **Full gate (matches CI):** `bash scripts/pre_deploy_gate.sh` — installs Chromium via npm first if you want the Playwright slice; on a quick loop use `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh`.
2. **SQLite locks (Windows):** If `migrate_gate_test_db` fails with **database is locked**, close other test runners and see [docs/TEST_DATABASE.md](docs/TEST_DATABASE.md) (`PRE_GATE_FRESH_TEST_DB=1` or a unique `DJANGO_TEST_DB_FILE` path).
3. **i18n catalog drift:** If the gate fails on `verify_i18n_catalog_fresh.py`, run `python manage.py sync_i18n_catalog --compile` and commit updated `locale/**` files.
4. **Operator Phase 10/11 slice (optional):** `python scripts/verify_operator_phase10_11_e2e.py` — use `--ux-db-file .django_test_dbs/<unique>.sqlite3` if the default file is locked.

CI: [.github/workflows/smoke.yml](.github/workflows/smoke.yml) runs the pre-deploy gate on **push/PR to `main`** (and can be triggered manually via **Actions → Smoke test → Run workflow**).

## Plan completion and dependencies

**Execution status:** [docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (At a glance, §11.4, §12) — single place for program gates and “what’s left.”

All plan items are complete; CI enforces the non-negotiables. Solid platform and dependency list: [docs/execution/PLATFORM_COMPLETION_AND_DEPENDENCIES.md](docs/execution/PLATFORM_COMPLETION_AND_DEPENDENCIES.md). Status: [docs/plan/UX_PLAN_FULL_COMPLETION_REGISTER.md](docs/plan/UX_PLAN_FULL_COMPLETION_REGISTER.md). Remaining track: migrate existing SiteSettings usages per [docs/security/SITESETTINGS_INVENTORY.md](docs/security/SITESETTINGS_INVENTORY.md).

## Other resources

- **Documentation governance:** [docs/documentation_governance_plan.md](docs/documentation_governance_plan.md)
- **Management commands:** [docs/MANAGEMENT_COMMANDS_INDEX.md](docs/MANAGEMENT_COMMANDS_INDEX.md), [docs/execution/MANAGEMENT_COMMAND_INVENTORY.md](docs/execution/MANAGEMENT_COMMAND_INVENTORY.md)
