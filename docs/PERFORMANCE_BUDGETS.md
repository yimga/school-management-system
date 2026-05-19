# Performance budgets (Wedge 2 / cross-cutting)

| Surface | p50 target | p99 target | Gate |
|---------|------------|------------|------|
| OneRoster GET /users (cached) | 200ms | 2s | Observability SLO dashboard |
| LTI launch redirect | 150ms | 1.5s | Section 8 metrics |
| Public API /api/v1/* auth | 100ms | 1s | API health |

**Fail gate (CI optional):** Set `PERF_BUDGET_STRICT=1` and run `scripts/check_performance_budgets.py` — exits non-zero if any budget row exceeds time/query limits.

**Zero-Ticket / configure hub (strict):** `/siteconfig/zero-ticket/` ≤40 queries / 1.2s; `/siteconfig/zero-ticket/permissions/` ≤35 / 1.0s; `/portal/configure/` ≤45 / 1.5s — `enforce: true` in `check_performance_budgets.py`.

**DOM node proxy (Chromebook):** `python scripts/verify_dom_performance_budgets.py` — element count caps: zero-ticket 2800, permissions 2200, backend dashboard 3500.

**N+1 caps (tests):** `apps/siteconfig/tests/test_performance_zero_ticket.py` — `run_tenant_diagnostics` ≤25 queries; permission simulator ≤20; hub render ≤45.

**N10 tighter smoke (partial):** With `PERF_BUDGET_STRICT=1`, also set `PERF_BUDGET_STRICT_N10=1` to apply **~25% stricter** time ceilings. Budgets include **anonymous `/marketing/`** (public landing) plus staff paths. **CI:** workflow **N10 performance budgets** (weekly + manual) sets `PERF_BUDGET_STRICT_GATE_ROWS=n10_public` so only the anonymous **`/marketing/`** row is enforced (avoids staff-path query noise under DEBUG). Full rows still run locally without that env. **Lighthouse:** `.github/workflows/lighthouse-ci.yml` when `LHCI_URL` is set; optional **`LHCI_URLS_EXTRA`** (comma-separated full URLs, same origin) for multi-path lab runs; optional **`LHCI_AUTO_EXTRAS=1`** appends the recommended same-origin bundle in `lighthouserc.cjs`; **`LHCI_STRICT_N10`** GitHub var → stricter thresholds. **RUM read path:** staff `GET /api/internal/north-star/rum-web-vitals/` ([RUM_HOOK.md](RUM_HOOK.md)). See [LHCI_CI_URLS.md](LHCI_CI_URLS.md) + `lighthouserc.cjs`. Full CWV on every PR still optional until RUM/LHCI is default.
