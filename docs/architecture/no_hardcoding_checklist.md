# No-hardcoding checklist (RunMyCampus)

**Rule:** Do not put tenant-, country-, or region-specific logic in app code. Use policy, `request.tenant_runtime`, or registries instead.

## CI check

Run before push or in CI:

```bash
python scripts/check_no_hardcoding.py
```

Use `--allow-tests` to ignore test files, `--exit-zero` to report but not fail.

## PR review checklist

- [ ] No `country == "XX"` or `tenant.country ==` in views, services, or forms (use `request.tenant_runtime.policy` or policy slices).
- [ ] No hardcoded region/country lists for behaviour (use policy, registries, or feature flags).
- [ ] No direct `school.settings` / `school.features` in app code (use `get_effective_policy(school)` or `request.tenant_runtime.policy`).
- [ ] Control plane and migration/seed code may reference country/region for provisioning; exclude from this rule where intentional.

## Allowed

- Reading `request.tenant_ctx.country` or `request.tenant_runtime.policy` for display or branching that is itself policy-driven.
- Registry seed data (e.g. currency by ISO code) and management commands that provision by region.
- Tests that assert policy behaviour for specific country/tenant when testing the policy layer.

## References

- `RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md` Part C (Core Architectural Rule).
- `docs/architecture/phase2_hardcoding_sweep.md` (historical).
- `apps/platform_runtime/` — `request.tenant_runtime.policy`.
