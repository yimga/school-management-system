# Phase SLO budgets

Authoritative list of SLO budgets gating each phase of the global governance program. The aggressive audit loop refuses to mark a phase `DONE` if the relevant SLO is breached on the latest 30-day window.

| Phase | Subject | SLO |
|-------|---------|-----|
| P0D | Matrix shard read | P95 latency < 50 ms cold / < 5 ms warm |
| P0D | Plan completion verifier | wall clock < 10 s |
| P1 | Language overlay resolution | error rate < 0.01 % of signup attempts |
| P2A | `Organization` model write | P95 latency < 25 ms |
| P2B | `governance_operating_mode` resolution | P95 latency < 5 ms |
| P3A | Matrix-driven runtime call | P95 latency < 50 ms cold / < 5 ms warm |
| P3B | Subdivision lookup | P95 latency < 20 ms |
| P3C | Multi-currency FX rollup | eventual consistency < 5 minutes |
| P3D | MC profile lookup | P95 latency < 30 ms |
| P4A | Group console first paint | LCP < 2.5 s p75 |
| P4C | Org billing FX rollup | eventual consistency < 5 minutes |
| P4D | EMIS export submission | success rate >= 99 % rolling 30-day |
| P4E | SMS multi-gateway failover | failover time < 30 s |
| P5 | Aggressive audit loop master gate | wall clock < 60 s |
| P6 (turbo) | Real-time compliance engine evaluation | P95 < 5 ms |
| P6 (turbo) | Sovereignty trust score refresh | freshness < 24 h |

## Enforcement

[`scripts/verify_phase_slo_budgets.py`](../scripts/verify_phase_slo_budgets.py) asserts this document exists and is non-empty. Telemetry collection is wired through `apps/observability/slo.py` (existing P10 observability pillar).

## Updating

Changes to SLO budgets require:

1. New or updated row in this document.
2. Corresponding `SLODefinition` in [`apps/observability/slo.py`](../apps/observability/slo.py).
3. SOT batch row capturing the change.
