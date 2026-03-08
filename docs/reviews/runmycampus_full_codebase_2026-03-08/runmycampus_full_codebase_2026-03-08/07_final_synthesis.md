# Final Synthesis

Date: 2026-03-08

## Completion Status

This review completed all planned waves:

- Wave 0: scope, inventory, baseline
- Wave 1: critical runtime/security/search remediations and targeted tests
- Wave 2: platform core, logic, hardcoding, product-surface analysis
- Wave 3: security, API, documents, compliance analysis
- Wave 4: synthesis, contradiction map, action list, ordered execution plan

## Contradiction Map

| Platform claim | Actual code state | Required resolution |
|---|---|---|
| tenant runtime is dominant | policy and nav still fall back to direct model/global singleton reads | make runtime the only supported owner |
| docs are complete and no-hardcoding aligned | hardcoded onboarding, nav, defaults, page detection, theme layers remain | rewrite docs to match current state, then close gaps |
| migration cloud exists | two import types, zero runs, no live rollback history | rebuild as job engine before marketing it as a platform capability |
| marketplace is installable | zero reviews in motion, zero installations, zero tenant blueprints | either activate fully or relabel as preview/internal |
| API is product surface | `/api/roadmap/*` exposes many stubs/backlog endpoints | move roadmap status out of production API space |

## Remediations Landed During Review

1. Tenant context now reads canonical school JSON fields.
   Files: `apps/tenancy/middleware.py`, `apps/tenancy/tests/test_tenant_context_middleware.py`

2. Passkeys now count consistently in MFA helper logic.
   Files: `apps/accounts/views_security.py`, `apps/accounts/tests/test_security_export_mfa.py`

3. Subject search is school-scoped and no longer serializes a missing field.
   Files: `apps/api/search_api.py`, `apps/api/tests/test_search_api_tenant_scope.py`

Verification:

- `python manage.py check`
- targeted Django tests for all three fixes

## Top 20 Actions

1. Make `get_effective_policy()` and runtime compilation the only supported source of tenant behavior in request-time code.
2. Remove remaining direct tenant-path fallbacks to `SiteSettings.get_solo()` where policy or registry data should own the decision.
3. Replace the dual nav system with one registry-driven sidebar source and template-only rendering.
4. Move onboarding choices to registries and blueprint/provisioning services.
5. Replace the migration wizard's in-request test client usage with service-layer and task-layer orchestration.
6. Expand migration types and require `MigrationRun` audit plus rollback snapshots for each supported type.
7. Restrict or remove `/api/roadmap/*` from the production API namespace.
8. Reduce `SchoolConfigAPI` to the minimum public bootstrap contract.
9. Define explicit search visibility policy by role and tenant, then implement it consistently across all search types.
10. Replace inline HTML 403 responses in compliance middleware with shared response handlers.
11. Seed and use `InstitutionTypeRegistry` so blueprint selection has a real institutional taxonomy.
12. Activate the tenant blueprint application path or stop presenting blueprint packs as installable tenant configuration.
13. Decide whether marketplace is production, preview, or internal-control-plane only, then align UI and docs to that answer.
14. Split `apps/accounts/views.py` into bounded modules.
15. Split `apps/siteconfig/models.py` and reduce cross-domain coupling in site configuration.
16. Reduce the base shell CSS stack and define a performance budget for default page loads.
17. Replace broad `except Exception` in middleware, runtime, and policy paths with explicit failure handling.
18. Add `pytest-django` and a repo-level pytest configuration so unit and middleware tests are first-class.
19. Add smoke tests for runtime compilation, nav rendering, onboarding registry choices, search scoping, and migration adapters.
20. Rewrite architecture index claims so they describe the real state, not the intended state.

## 90-Day Engineering Plan

### Days 1-15

1. Freeze new platform-surface additions.
2. Define the runtime ownership rule and block new direct tenant config reads in code review.
3. Finish search visibility hardening.
4. Normalize MFA and compliance response contracts everywhere.

### Days 16-30

5. Replace sidebar fallback trees with one nav registry plus renderer.
6. Remove hardcoded onboarding country and flavor sources in favor of registries and blueprint selection.
7. Rewrite architecture index and core platform docs to match actual code.

### Days 31-45

8. Extract migration logic from `apps/accounts/views.py` into dedicated adapters and tasks.
9. Remove Django test client usage from production request flow.
10. Add real run history, rollback snapshots, and operator scorecards.

### Days 46-60

11. Decide marketplace operating mode: production, preview, or internal.
12. Wire tenant blueprint application end to end.
13. Seed `InstitutionTypeRegistry` and tie it into onboarding and blueprint application.

### Days 61-75

14. Add `pytest-django`, `pytest.ini`, and a fast test path.
15. Split oversized files starting with `apps/accounts/views.py` and `apps/siteconfig/models.py`.
16. Reduce base-shell CSS layering and set bundle/page budgets.

### Days 76-90

17. Remove or relocate roadmap stub endpoints from the production API namespace.
18. Harden public bootstrap endpoints and tenant-facing document/compliance boundaries.
19. Add release gates for runtime dominance, no-hardcoding checks, nav registry use, and search scoping.
20. Re-run this audit and require that every item be marked implemented, intentionally retained, or deleted.

## Final Verdict

The codebase is past the prototype stage, but not yet at platform coherence. The right next move is consolidation, not expansion. The good news is that the gaps are understandable and mostly tractable. The bad news is that leaving the mixed-mode architecture in place will make every future feature slower, harder to verify, and easier to misdocument.
