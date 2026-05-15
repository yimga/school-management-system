# Service Level Objectives — code-defined SOT

**SOT module:** [`apps/observability/slo.py`](../apps/observability/slo.py)
**Tests:** [`apps/observability/tests/test_slo.py`](../apps/observability/tests/test_slo.py)
**Dashboard:** see `api_operational_slo_dashboard` in [apps/observability/views.py](../apps/observability/views.py) line 1223
**Companion:** [`OBSERVABILITY_SLO.md`](OBSERVABILITY_SLO.md) (operator runbook)

## Why SLOs live in code

For SOC 2 evidence and on-call sanity, the platform's SLO targets are
encoded as immutable `SLODefinition` instances in
`apps/observability/slo.py`. They are not configuration — drift
produces a diff, the alert taxonomy belongs in code review.

The dashboard reads from this module; the burn-rate evaluator computes
multi-window severity using the standard Google SRE thresholds
(Workbook ch. 5).

## Current SLO set (2026-05-14, wave NS-3)

| Key | Target | Window | Kind | Threshold | Backed by |
|---|---|---|---|---|---|
| `web.availability` | 99.9% | 30d | 5xx-free rate | — | `http.server` |
| `attendance.submit` | p95 ≤ 800ms 95% of the time | 7d | latency | 800ms | `attendance.submit` |
| `grade.entry` | p95 ≤ 900ms 95% of the time | 7d | latency | 900ms | `grade.entry` |
| `parent.dashboard` | p95 ≤ 1200ms 95% of the time | 7d | latency | 1200ms | `parent.dashboard.render` |
| `migration.bundle_apply` | 99.0% success | 30d | availability | — | `migration.bundle_apply` |
| `ai.gateway.latency` | p95 ≤ 2500ms 95% of the time (ollama) | 7d | latency | 2500ms | `ai.gateway.invoke` |
| `webhook.delivery` | 99.0% success | 30d | availability | — | `webhook.deliver` |
| `sync.conflict_pending` | 99.0% fresh | 7d | freshness | — | `sync.delta_apply` |

## Burn-rate alert taxonomy

```
1h  window, burn >= 14.4  → page   (2% of monthly budget in 1h)
6h  window, burn >= 6.0   → page   (5% of budget in 6h)
1d  window, burn >= 3.0   → ticket (10% of budget in 1d)
3d  window, burn >= 1.0   → ticket (10% of budget in 3d)
any window, burn >= 0.5   → watch
otherwise                 → ok
```

`apps.observability.slo.burn_rate_severity(burn=..., window_minutes=...)`
is the canonical helper.

## Custom Sentry transactions wired this wave

The transactions named above are wired via
[`apps/observability/tracing.py`](../apps/observability/tracing.py)'s
`trace_view(name)` decorator, applied to:

| Transaction | Code path |
|---|---|
| `attendance.submit` | `apps/academics/api_views.py` `AttendanceViewSet.create` |
| `grade.entry` | `apps/academics/api_views.py` `GradeViewSet.create` |
| `parent.dashboard.render` | `apps/portal/views_parent.py` `parent_dashboard` (already wired pre-wave) |
| `migration.bundle_apply` | `apps/migration_cloud/orchestrator.py` `apply_bundle` (uses raw `sentry_sdk.start_transaction` since this is a task, not a view) |

When `sentry_sdk` is unimportable or `SENTRY_DSN` is unset, the
decorator is a no-op — test envs don't pull in the SDK.

## Adding a new SLO

1. Append a `SLODefinition(...)` to the `SLOS` tuple in
   `apps/observability/slo.py`.
2. If it backs a hot path that needs named tracing, decorate the view /
   task with `@trace_view("<txn_name>")` and reference that name in the
   `sentry_transactions` tuple.
3. Add a test case to `test_slo.py` that asserts the key is present.
4. Update the dashboard if the new SLO needs its own card.

## Anti-patterns

- **Don't put SLO targets in Django settings.** Settings are
  per-environment; SLOs are per-product-promise and should not vary
  between staging and prod.
- **Don't add a custom transaction without backing it with an SLO.**
  Telemetry without a target is noise.
- **Don't lower a target to silence an alert.** Either fix the burn or
  declare in writing that the promise has changed.
