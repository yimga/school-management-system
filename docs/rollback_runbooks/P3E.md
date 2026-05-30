# Rollback runbook: Phase 3E exit

## Trigger conditions

- Matrix-driven runtime call P95 regresses >2x baseline.
- `verify_subdivision_coverage.py` reports a sovereign state silently dropping subdivision data.
- `verify_global_operational_blind_spots.py` flips a known-good blind spot back to red.
- Multi-currency FX rollup eventual consistency exceeds the SLO budget.

## Safe revert

1. Flip `MATRIX_RUNTIME_BINDING_ENABLED=False`, `MULTI_CURRENCY_FX_ROLLUP_ENABLED=False`, and any other Phase 3 feature flags off.
2. `git revert` the merge commit for the failing sub-phase (3A / 3B / 3C / 3D) rather than the entire phase if isolation is possible.
3. Reset register status for the affected sub-phase IDs to `IN_PROGRESS`.
4. Confirm runtime returns to pre-Phase-3 latency profile via Sentry / observability.

## Forbidden

- Disabling the matrix verifiers to "make CI green".
- Truncating subdivision data to side-step a verifier failure.
