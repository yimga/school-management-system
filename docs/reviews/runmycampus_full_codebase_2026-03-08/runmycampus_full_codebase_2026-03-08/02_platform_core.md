# Platform Core

Date: 2026-03-08

## Core Conclusion

The platform core is directionally correct but not yet dominant. The repo has runtime objects, policy layers, blueprint models, registry models, and a tenant context. The problem is that these layers do not yet own enough of the behavior that matters.

## 1. Tenant Context

Observed:

- `apps/tenancy/middleware.py` now builds `TenantContext` from `School.features` and `School.settings`, with fallback to legacy alias names.
- Before this review, the middleware was reading `features_json` and `settings_json`, which are not the canonical `School` model fields.
- The `School` model defines `settings` and `features` at `apps/schools/models.py:122-131`.

Meaning:

- A large part of the runtime contract depends on `request.tenant_ctx`.
- If that object is wrong, every downstream runtime claim becomes suspect.

Status:

- fixed in this review
- covered by `apps/tenancy/tests/test_tenant_context_middleware.py`

## 2. Policy Dominance Is Not Real Yet

Observed:

- `apps/policies/resolver.py:158-210` merges `School.settings` and `School.features` directly.
- `apps/policies/resolver.py:212-267` backfills key decisions from `SiteSettings.get_solo()`.
- hardcoded fallback values still exist for admissions and grade approval.

Impact:

- modules cannot rely on policy resolution as a pure registry/runtime output
- tenant behavior is still partly an ad hoc merge of tenant JSON and global singleton fallbacks

Required direction:

1. keep `get_effective_policy()` as the only supported entry point
2. stop introducing new direct reads of `School.settings`, `School.features`, and `SiteSettings.get_solo()` in tenant code
3. move fallback defaults into typed registry/bootstrap data

## 3. Governed Navigation Is Still Partially Fictional

Observed:

- `templates/partials/portal_sidebar.html:47-65` claims config-driven order
- `templates/partials/portal_sidebar.html:66-220` still contains a large fallback tree with role branches and duplicated sections
- `apps/siteconfig/portal_sidebar_items.py:179-366` is itself a hardcoded menu construction engine

Impact:

- the code has two competing owners for navigation
- docs can say nav is governed, but the product still behaves like code-owned navigation with configuration hints

Required direction:

1. define a single nav registry source
2. reduce templates to rendering only
3. migrate role branching into registry metadata and runtime filters

## 4. Search Is Partially Runtime-Aware, Partially Unsafe

Observed:

- student, teacher, classroom, and invoice searches partially respect `request.school`
- subject search did not; that is now fixed in `apps/api/search_api.py:272-285`
- classroom search remains school-scoped but not meaningfully role-scoped

Impact:

- search is one of the fastest routes to tenant leakage because it is broad by design
- mixed scoping rules produce inconsistent trust boundaries

Status:

- subject leakage fixed in this review
- classroom and role-level search visibility still need explicit policy design

## 5. Onboarding Is a Placeholder Shell, Not a Registry-Driven Platform Flow

Observed:

- `templates/schools/onboard_wizard.html:12` explicitly says the shell exists while provisioning services evolve
- `templates/schools/onboard_wizard.html:17-23` hardcodes only four countries

Impact:

- the product presents onboarding as a generalized platform flow
- the implementation is still a thin compatibility shell

Required direction:

1. source country and education-system options from registries
2. move onboarding flavor selection into blueprint and provisioning services
3. make the shell a pure renderer over registry/runtime choices

## 6. Migration Cloud Is Not Yet a Platform Engine

Observed:

- `apps/accounts/views.py:1999` defines only `students` and `grades`
- `apps/accounts/views.py:2046` caps upload preview at 500 rows
- `apps/accounts/views.py:2108` imports `django.test.Client` in a live request path
- `apps/accounts/views.py:2115` posts to `api:entity-student-bulk-commit` through that test client
- `apps/accounts/views.py:2152-2153` directly calls `preview_import()` and `apply_import()`
- database snapshot: `migration_runs = 0`, `rollback_ready = 0`

Impact:

- this is not yet an operational migration engine
- it is a narrow import wizard with partial reuse of API/service code

Required direction:

1. remove the in-request test client pattern
2. formalize import jobs as services/tasks with typed adapters
3. expand import families beyond students and grades
4. make rollback and run history real before marketing the migration cloud as a platform capability

## 7. Landed Fixes In This Wave

Implemented and verified:

- `apps/tenancy/middleware.py`
- `apps/accounts/views_security.py`
- `apps/api/search_api.py`

Tests:

- `apps/tenancy/tests/test_tenant_context_middleware.py`
- `apps/accounts/tests/test_security_export_mfa.py`
- `apps/api/tests/test_search_api_tenant_scope.py`

## Platform-Core Verdict

The foundation is salvageable and worth continuing. The next platform milestone should not be "add more modules." It should be "make runtime, policy, navigation, search, and migration the actual owners of behavior."
