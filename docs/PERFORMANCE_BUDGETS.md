# Performance Budgets (Path-to-10)

**Non-negotiable:** Critical pages and flows have defined response-time and query-count budgets. Enforcement may be phased (warn in CI first, then fail).

## Budget definitions

| Surface | Response time (p95) | Query count (max) | Notes |
|---------|---------------------|--------------------|-------|
| Role home (backend dashboard) | 1.2 s | 25 | Per-request DB queries |
| Setup Studio (guided onboarding) | 1.5 s | 35 | Includes payload + recommendations |
| Tenant app catalog | 1.0 s | 20 | List + compatibility |
| Package apply (API) | 5.0 s | 50 | Single apply transaction |
| Runtime inspector | 0.8 s | 15 | Per-school inspection |
| Control plane dashboard | 2.0 s | 40 | Super dashboard |
| Metadata catalog view | 1.0 s | 30 | Catalog + lineage |

## Enforcement

- **Phase 1:** Budgets are documented; manual and automated profiling can compare against these numbers.
- **Phase 2 (in place):** `scripts/check_performance_budgets.py` runs smoke requests for role home, Setup Studio, and metadata catalog; when `PERF_BUDGET_STRICT=1` it fails the gate. Pre-deploy gate runs it when `PERF_BUDGET_STRICT=1` (see `scripts/pre_deploy_gate.sh`).
- **Phase 3:** Per-request middleware or APM that records p95 and query count per route and alerts when over budget.

## Query budgets

- Prefer `select_related()` / `prefetch_related()` for role-home and catalog views.
- Avoid N+1 in list views; use `annotate` or batched lookups where needed.
- Package engine: keep transaction scope minimal; read-heavy work outside the atomic block where safe.

## References

- `docs/PATH_TO_10_SCORECARD.md` — Path-to-10 execution
- `scripts/pre_deploy_gate.sh` — Full gate (performance budget check optional)
