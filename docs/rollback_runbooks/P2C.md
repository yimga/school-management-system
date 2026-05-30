# Rollback runbook: Phase 2C exit

## Trigger conditions

- `verify_school_operating_modes.py` fails: a `School` cannot resolve its `governance_operating_mode`.
- `verify_hierarchy_silo_drift.py` reports unsynced `mat_groups` vs `parent_school` subtrees.
- Migration `apps/governance/migrations/00XX_*` errors on a real tenant DB.
- Standalone-mode tenants experience any behavior change attributable to Phase 2.

## Safe revert

1. `python manage.py migrate governance <previous_leaf>` to roll back the schema delta.
2. `git revert` the merge commit on `main`.
3. Restore feature flags to off (`GOVERNANCE_ORG_LAYER_ENABLED=False`).
4. Re-run `verify_school_operating_modes.py` and `verify_hierarchy_silo_drift.py` to confirm the reverted tree is clean.
5. Customer comms: send the prepared "no behavior change" template to anyone in the rollout cohort.

## Forbidden

- `python manage.py migrate --fake` to skip the reverse.
- Editing existing Organization rows in production without an `OrganizationLifecycleEvent`.
