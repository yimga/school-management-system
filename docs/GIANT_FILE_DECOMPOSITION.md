# Giant-file decomposition (Phase 10 — 2.1)

**Purpose:** Split oversized app files by bounded domain and enforce line thresholds in CI so the codebase stays maintainable.

**CI:** `scripts/lint_mega_files.py` runs in pre-deploy gate. With `CODEX_STRICT=1` it fails when any file in `apps/` exceeds the threshold. Default: **4500 lines**; lower to 3500 after siteconfig/models and schools/marketing_views are split.

---

## Target files (priority order)

| File | Current goal | Notes |
|------|----------------|------|
| `apps/siteconfig/models.py` | &lt; 2500 | **Started:** AI models moved to `siteconfig/models_ai.py`; re-export from `models.py`. |
| `apps/accounts/views.py` | &lt; 1500 | Split by domain: auth, dashboard, profile, approvals, etc. |
| `apps/schools/super_views.py` | &lt; 1500 | **Started:** migration cloud, profile registry, rollback, sync_repair → `super_views_migration.py` (re-exported). Remainder: dashboard, tenant CRUD, runtime inspector, workflow simulator, etc. |
| `apps/portal/views.py` | &lt; 1500 | **Done:** parent_finance, parent_wallet, parent_feed → `views_parent_finance.py`. |
| `apps/finance/views.py` | &lt; 1200 | **Done:** finance_reports, submit_report_request → `views_reports.py`. |
| `apps/api/views_v1.py` | &lt; 1200 | **Done:** Intervention* views → `views_v1_intervention.py`. |

---

## How to split

1. **Create domain modules** (e.g. `accounts/views_auth.py`, `accounts/views_dashboard.py`).
2. **Move views and URL patterns** into the new modules; keep `urls.py` importing from them.
3. **Re-export in `views.py`** for backward compatibility if other code does `from app.views import view_name`.
4. **Run** `python scripts/lint_mega_files.py` (or `CODEX_STRICT=1` in pre_deploy_gate) to enforce.

---

## Stricter thresholds per file (optional)

To fail only when a *listed* file exceeds a custom line count, extend `lint_mega_files.py` with a `TARGET_FILES` dict (path → max_lines) and check those first; otherwise use default.

---

**Reference:** `docs/PHASE_10_BACKLOG.md`, `docs/PHASE_10_NEXT_STEPS.md`.
