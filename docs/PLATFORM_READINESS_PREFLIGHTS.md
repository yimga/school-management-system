# Platform readiness preflights — SOT for flip-the-switch ops decisions

The platform has several boolean toggles that change behavior in
production (`DATA_RESIDENCY_ENFORCE`, `CSP_ENFORCE`, future ones).
Flipping any of them without verifying preconditions is destructive:
misconfigured-enforce-mode 500s every misaligned request.

Each toggle has a corresponding **readiness preflight** that asserts
its preconditions. This doc is the operator-facing index plus the
runbook for the unified `verify_platform_readiness` command.

## Unified surface

```
python manage.py verify_platform_readiness               # all sections
python manage.py verify_platform_readiness --json
python manage.py verify_platform_readiness --section residency csp
python manage.py verify_platform_readiness --section baselines
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | every requested section is ready |
| 1 | at least one section reports preconditions unmet |
| 2 | invocation error (settings missing, subprocess failed) |

## Sections

### `residency` — `DATA_RESIDENCY_ENFORCE` preflight

Backed by `apps/schools/residency_readiness.py::assess_readiness()`
(Wave K4).

Checks:

* Every active regulatory region in use has a matching
  `replica_<region>` alias in `settings.DATABASES`.
* No active school has `regional_cluster ≠ effective_region`.
* No active school has a blank `data_region` whose `country_code`
  maps to a non-`global` derived region.

To flip `DATA_RESIDENCY_ENFORCE=True` safely:

1. Provision a Postgres replica per regulated region.
2. Export `DATA_RESIDENCY_REPLICA_<REGION>=<DATABASE_URL>` env vars.
3. Restart workers (settings.py reads the env vars at boot).
4. Run `python manage.py verify_data_residency --fix-derive` until
   the per-tenant report is clean.
5. Run `python manage.py verify_platform_readiness --section residency`
   until exit 0.
6. Set `DATA_RESIDENCY_ENFORCE=1` (env var or settings override).

### `csp` — `CSP_ENFORCE` preflight

Backed by `apps/security/csp_readiness.py::assess_csp_readiness()`
(Wave L2 + L-followup).

Checks:

* `ContentSecurityPolicyMiddleware` wired in `settings.MIDDLEWARE`.
* `CSP_REPORT_URI` non-empty.
* All 5 required directives present (`default-src`, `script-src`,
  `object-src`, `frame-ancestors`, `base-uri`).
* `script-src` lacks `'unsafe-inline'` and `'unsafe-eval'`.
* (Informational) Runtime violation counters from the cache-backed
  hourly buckets — last hour + last 24h + per-directive breakdown.

To flip `CSP_ENFORCE=True` safely:

1. Run `python manage.py verify_platform_readiness --section csp` —
   exit 0 confirms config preflight clean.
2. Watch the warning log stream for `csp_violation` events for an
   ops-appropriate window (Anthropic-style: **7+ days for production**).
   The runtime counters in the preflight give a quick "are we seeing
   activity?" check, but logs are the canonical surface.
3. If violation rate is acceptable (or known leaks captured via
   `CSP_EXTRA_*` allowlists), set `CSP_ENFORCE=1`.

Known debt that is **not** a blocker:

* `style-src 'unsafe-inline'` — tracked under
  `scan_inline_style_off_token` (zero-tolerance CI gate post-v2.27).
  Style-CSP buys less defense than script-CSP; not worth gating on.

### `rls` — Row-Level Security runtime preflight (Wave O2)

Backed by `apps/schools/rls_readiness.py::assess_rls_readiness()`.

Checks:

* `TenantMiddleware` wired in `settings.MIDDLEWARE`.
* `apps.schools.rls_context.set_rls_school_id` is importable.
* `USE_DJANGO_TENANTS=False` (RLS mode, not schema mode — schema mode
  silently bypasses RLS policies).
* **Postgres-only**: `SET app.current_school_id = '0'` succeeds against
  the default DB. Skipped on SQLite (dev) — the GUC contract is
  production-only.
* **Postgres-only**: at least one entry in `pg_policies` for the
  public schema. Zero policies means migration 0048
  (`schools.0048_force_rls_on_all_enabled_tables`) didn't run or was
  rolled back — RLS is structurally broken.

Skipped checks are reported as `skipped` rather than failed — the
preflight passes on dev/SQLite. To get the full check, run on a
Postgres-backed deployment.

To investigate suspected RLS regression in production:

1. `python manage.py verify_rls_readiness` on the production DB.
2. If `pg_policies` count is 0: re-apply migration 0048
   (it's idempotent under `IF NOT EXISTS` policy syntax).
3. If `USE_DJANGO_TENANTS=True` on a tenant subdomain that should
   be RLS-mode: fix env var and restart.
4. If GUC unsettable: check Postgres role permissions — `SET` on
   `app.*` requires the role grant.

### `at_risk` — at-risk ML artifact preflight (Wave O1)

Backed by `apps/analytics/at_risk_readiness.py::assess_at_risk_readiness()`.

Three states the predictor can be in:

* `heuristic` — no artifact path configured anywhere. The platform isn't
  broken; it's using rule-based scoring. Ready=True.
* `ml-artifact` — path resolves, artifact loads, bundle shape valid.
  Predictor will use the ML inference path. Ready=True.
* `misconfigured` — path is set (via `settings.AT_RISK_MODEL_PATH`,
  env var, or `AT_RISK_MODEL_DIR/at_risk_v1.joblib` auto-discovery)
  but the file is missing / unloadable / wrong shape. The predictor
  would **silently fall back to heuristic** without anyone noticing —
  the dangerous state this preflight catches. Ready=False.

To enable ML mode:

1. `python manage.py train_at_risk_baseline --clear-cache` (writes
   synthetic baseline to `var/at_risk/at_risk_v1.joblib`), OR
2. Set `AT_RISK_MODEL_PATH=/path/to/your.joblib` (env or settings).
3. `python manage.py verify_at_risk_readiness` to confirm mode flipped
   to `ml-artifact`.
4. `python manage.py score_student_risk --reload --student <id>` to
   see the predictor actually use the artifact (`path=ml-artifact`).

For production retraining loop, see
`apps/analytics/management/commands/export_at_risk_training_data.py`
(Wave O4) + `/portal/at-risk/labeling/` for label collection.

### `baselines` — documented scanner baseline drift (Wave N)

Backed by `scripts/check_documented_baselines.py` (this wave).

Each architectural CI scanner has THREE numbers that should agree:

1. The integer in **`CLAUDE.md`**'s scanner table (hand-maintained).
2. The `finding_count` (or `total` / `len(findings)`) in
   `var/security-audit-baseline-<scanner>.json` (CI gate input).
3. The scanner's **current output** when re-run (the live state).

CI catches #2 vs #3 drift on every PR. Pre-Wave N, **#1 vs #2 drift
slipped through silently** — exactly the failure mode that bit Wave
L1a, where CLAUDE.md said `742` long after the JSON had moved to `734`.

The `baselines` section catches this. Zero-tolerance gates legitimately
document `0` without a JSON file; non-zero documented numbers without
a JSON baseline are flagged as misleading.

### `--full` mode (baselines only)

The standalone script `scripts/check_documented_baselines.py --full`
additionally re-runs every scanner and reports current state vs
baseline (the existing CI gate, bundled for ops). Not exposed via the
Django command because it can take 60+ seconds when many scanners
walk the tree.

## CI wiring

The drift checker runs in
[`.github/workflows/architectural-boundaries.yml`](../.github/workflows/architectural-boundaries.yml)
as the `documented-baselines` job. CI fails when CLAUDE.md and a
`var/*.json` disagree.

## Adding a new preflight

When introducing a new `<FEATURE>_ENFORCE` toggle:

1. Build the underlying enforcement logic.
2. Build a `<feature>_readiness.py` module with `assess_<feature>_readiness()`
   returning a dataclass `<Feature>ReadinessReport` (mirror K4 / L2 shape:
   `ready: bool`, `issue_count() -> int`, structured detail fields).
3. Build a `verify_<feature>_readiness` standalone Django management
   command (one-section drilldown).
4. Add a new `_<feature>_section()` method to `verify_platform_readiness`
   and register it in the `SECTIONS` tuple.
5. Document the runbook in a new section of this file.
6. Tests at the underlying module level + at the orchestrator level.

The pattern is intentionally consistent — every preflight should
read the same way (`ready`, `issue_count`, details), so operators
don't need to relearn the surface per feature.
