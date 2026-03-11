# Giant-file decomposition (Phase 10 — 2.1)

**Purpose:** Split oversized app files by bounded domain and enforce line thresholds in CI so the codebase stays maintainable.

**CI:** `scripts/lint_mega_files.py` runs in pre-deploy gate. With `CODEX_STRICT=1` it fails when any file in `apps/` exceeds the threshold. Default threshold: **5000 lines** (reduce over time, e.g. 3500 → 2500).

---

## Target files (priority order)

| File | Current goal | Notes |
|------|----------------|------|
| `apps/siteconfig/models.py` | &lt; 2500 | **Started:** AI models moved to `siteconfig/models_ai.py`; re-export from `models.py`. |
| `apps/accounts/views.py` | &lt; 1500 | Split by domain: auth, dashboard, profile, approvals, etc. |
| `apps/schools/super_views.py` | &lt; 1500 | Split: super dashboard, tenant CRUD, runtime inspector, workflow simulator, etc. |
| `apps/portal/views.py` | &lt; 1500 | Split: dashboard, documents, features, AI gateway, etc. |
| `apps/finance/views.py` | &lt; 1200 | Split: invoices, fees, reports, permissions. |
| `apps/api/views_v1.py` | &lt; 1200 | Split by resource: dashboard, schools, reports, etc. |

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
