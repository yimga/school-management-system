# Rollback runbook: Phase 0D exit

## Trigger conditions

- `verify_country_governance_matrix.py` regresses to fewer than 249 verified shards.
- `verify_country_dissection_ledger.py` reports a wave-exit gate that should be `verified` but is `skeleton`.
- Master verifier `verify_global_governance_plan_completion.py --phase-max 0D` exits non-zero.
- Matrix shard read P95 latency regresses >2x baseline on a CI run.

## Safe revert

1. Stop any in-flight wave merges (`AUDIT` coordinator owns the merge queue).
2. `git revert` the offending merge commit instead of `reset --hard`.
3. Re-run the regulatory_matrix shard extender against the reverted tree to restore Phase 0X blocks.
4. Reset register status of affected items from `DONE` to `IN_PROGRESS`.
5. Recompute `status_counts` and re-emit the register.
6. Add a SOT §11.4 amendment row describing the rollback.
7. Open a follow-up batch for the lane that produced the regression.

## Forbidden during rollback

- `git push --force` on `main`.
- Editing past §11.4 rows; rollback gets its own row.
- Disabling the `global-governance-plan-completion` CI job.
