# SLO and observability targets (BR-01)

| Metric | Target | Notes |
|--------|--------|-------|
| API p50 | ≤ 800 ms | Core list/read/save |
| API p99 | ≤ 2000 ms | |
| Dashboard LCP | ≤ 2500 ms | |
| Uptime SLO | 99.9% monthly | Documented; measure in prod |

**Surfaces:** `/health/`, `/api/v1/slo-dashboard/` (if enabled), Prometheus `/metrics/`.

**Strict gate:** `PERF_BUDGET_STRICT=1` + `scripts/check_performance_budgets.py` in pre_deploy_gate.

**API:** `GET /api/internal/br/slo-targets/` returns JSON for operator dashboards.

*North-star: N9, N10, N11.*
