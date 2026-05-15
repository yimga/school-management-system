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
