# Performance budgets (Wedge 2 / cross-cutting)

| Surface | p50 target | p99 target | Gate |
|---------|------------|------------|------|
| OneRoster GET /users (cached) | 200ms | 2s | Observability SLO dashboard |
| LTI launch redirect | 150ms | 1.5s | Section 8 metrics |
| Public API /api/v1/* auth | 100ms | 1s | API health |

**Fail gate (CI optional):** Set `PERFORMANCE_BUDGET_GATE=1` and run `scripts/check_performance_budgets.py` when wired to k6 or prod metrics export. Until metrics are automated, manual review each release per NORTH_STAR N1–N29 in SOT.
