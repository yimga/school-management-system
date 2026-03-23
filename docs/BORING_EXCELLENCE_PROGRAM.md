# Boring excellence program

**Purpose:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §10.5.8 and [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md). Recurring discipline so the platform does not decay.

**Authority:** This doc defines the program; CI and scheduled tasks implement it. Completion gate: program doc exists; at least three of the checks are automated or in CI; rest on a schedule.

---

## Recurring checks (CI or scheduled)

| Check | Status | Where / how |
|-------|--------|-------------|
| **Dead button/link detection** | In CI | `scripts/phase_h_audit.py` (URL reverse; `--live` for live reverse); Phase H URL tests in `test_phase_h_ux_verification`, `test_smoke_urls`. |
| **Docs truth audits** | In CI / ledger | BACKLOG and docs_truth_ledger reconciled; SOT **§0** + §12 (**MET**). Step 25 reconciliation; PLAN_VERIFICATION_REPORT banner. |
| **Observability gaps** | Partial | Observability app: healthz, api_health, db_liveness, SLO dashboard; structured logging with `log_exception_with_context`; pre_deploy_gate runs smoke and Phase H. |
| **Permission drift** | Manual / backlog | AI permission matrix (get_ai_permission_for_user); staff-only tasks; public_endpoint_audit; lint_csrf_exempt_usage, lint_allow_any_usage in pre_deploy_gate. |
| **Accessibility audits** | In CI | `phase_h_audit.py` (skip-to-main link, viewport/frame); responsive/CSS warnings reported when present. Optional: expand a11y checks. |
| **Performance budgets** | Not yet | Placeholder: add Lighthouse or bundle-size budgets when front-end build is formalized. |
| **Route maturity scoring** | Partial | Phase H URL reverse tests; phase_h_audit static + --live; critical paths in PhaseHCriticalPathsTests. |
| **Stale flag cleanup** | Backlog-led | Feature toggles and governor limits in runtime; no dedicated "stale flag" linter yet. |
| **Duplicate shell detection** | Manual / §8.0 | UI/UX unification (one shell); OPERATING_DISCIPLINE_LAYERS §8.0; template audit in CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL. |
| **Unused model/page cleanup** | Incremental | LEGACY_PATH_INVENTORY; subtractive cleanup per migration; BACKLOG §2d. |
| **Config sprawl detection** | Partial | site_settings_usage_inventory; domain_ownership; SITECONFIG_OWNERSHIP_MIGRATION; lint_tenant_settings. |
| **Exception and secret discipline** | In CI | `lint_broad_except --strict`, `lint_secret_exposure`, `lint_raw_sql_usage` in pre_deploy_gate. |

---

## CI entry points

- **Full gate:** `bash scripts/pre_deploy_gate.sh` — runs lint_secret_exposure, lint_raw_sql_usage, lint_broad_except --strict, lint_no_print, manage check, ruff F401/F841, Phase H smoke + URL tests, phase_h_audit (static + --live when available).
- **Phase H only:** `bash scripts/run_phase_h_verification.sh` — smoke URLs, Phase H URL reverse tests, phase_h_audit.
- **Lints only:** Run individual scripts under `scripts/` (lint_*.py) and `manage.py check`.

---

## Schedule (non-CI)

| Check | Schedule | Owner |
|-------|----------|--------|
| Step 25 reconciliation | After each milestone | Agent / lead |
| BACKLOG §2e table update | When a row is completed | Agent doing the work |
| Docs truth ledger | When completion status changes | Agent / lead |
| Permission and endpoint audit refresh | Before release | Security / ops |
| Stale flag / config sprawl deep audit | Quarterly or per backlog | Backlog |

---

## Status

- **Program doc:** This file.
- **Automated in CI:** Dead link/URL reverse (phase_h_audit, Phase H tests); docs truth (ledger + BACKLOG policy); observability (health, logging, pre_deploy_gate); exception/secret/raw-SQL lints; accessibility (phase_h_audit skip-link, viewport).
- **On schedule / incremental:** Permission drift, config sprawl, unused model cleanup, performance budgets, route maturity expansion.
