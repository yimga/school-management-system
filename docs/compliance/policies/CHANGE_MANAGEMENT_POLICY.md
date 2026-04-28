# Change management policy (repository)

## Scope

Application and infrastructure-as-code changes tracked in Git for this monorepo.

## Required practices

1. **Traceability:** meaningful commits; large work recorded in `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` §11.4 when shipping a batch.
2. **Mechanical gates:** run targeted `scripts/verify_*` and `manage.py test` slices named in the batch or release checklist before merge.
3. **Generated artifacts:** when allowlists or inventories change, regenerate per script docstrings (e.g. `generate_platform_inventory.py --write`).

## Not in scope

External CAB minutes, customer change windows, and production deployment approvals live outside this repository.
