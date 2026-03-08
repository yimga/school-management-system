# Master Audit

Date: 2026-03-08

## Executive Summary

The codebase contains real platform-building work, but it does not currently satisfy its own architecture claims about runtime dominance, governed navigation, and no hardcoding. The dominant pattern is mixed-mode operation: newer runtime and registry layers exist, but major user-facing flows still bypass them through hardcoded templates, direct `School.settings` and `School.features` reads, `SiteSettings.get_solo()` fallbacks, and API stubs presented inside the production namespace.

The result is not that the platform is empty. The result is that the platform is structurally split between:

- a genuine multi-tenant/runtime direction
- a large compatibility shell that still behaves like a single-tenant app with tenant overlays

## Highest-Risk Findings

1. Critical: tenant context assembly was reading non-existent school JSON aliases in the main request path.
   Evidence: `apps/tenancy/middleware.py:38-52`, `apps/tenancy/middleware.py:64-75`, `apps/schools/models.py:122-131`
   Effect: `request.tenant_ctx.feature_flags` and `request.tenant_ctx.policy_overrides` could silently degrade to empty dicts.
   Status: fixed in this review.

2. High: policy resolution still merges direct tenant JSON and single-tenant fallbacks instead of making runtime/registry the dominant owner.
   Evidence: `apps/policies/resolver.py:158-210`, `apps/policies/resolver.py:212-267`
   Effect: platform behavior remains partly controlled by ad hoc tenant JSON plus `SiteSettings.get_solo()` fallback defaults like `GIL` and `["DEAN", "HOD"]`.

3. High: the architecture index claims the core docs are complete and aligned with no hardcoding, but the runtime still depends on major hardcoded template and view logic.
   Evidence: `docs/architecture/README.md:3-5`, `docs/architecture/README.md:13-18`
   Effect: engineering and product decisions can be made from documentation that overstates platform maturity.

4. High: global search had tenant data leakage and a live serializer/runtime defect on subject results.
   Evidence before fix: `apps/api/search_api.py:272-285`
   Effect: subject search ignored school scoping and attempted to serialize a non-existent `Subject.code`.
   Status: fixed in this review.

5. High: MFA policy was internally inconsistent for passkey-only users.
   Evidence: `apps/accounts/middleware.py:373-389`, `apps/accounts/views_security.py:75-100`
   Effect: passkeys counted in middleware but not in export authorization helper.
   Status: fixed in this review.

6. High: the migration cloud is not production-grade despite UI language that suggests a generalized migration system.
   Evidence: `apps/accounts/views.py:1999`, `apps/accounts/views.py:2046`, `apps/accounts/views.py:2108`, `apps/accounts/views.py:2115`, `apps/accounts/views.py:2152-2153`
   Effect: only a narrow import surface exists, uploads are capped, preview/apply paths are coupled to request-time flow, and one request path uses Django's test client inside production logic.

7. Medium-High: governed navigation is not yet governed; it is duplicated across template fallback branches and a hardcoded Python builder.
   Evidence: `templates/partials/portal_sidebar.html:47-65`, `templates/partials/portal_sidebar.html:66-220`, `apps/siteconfig/portal_sidebar_items.py:179-186`, `apps/siteconfig/portal_sidebar_items.py:208-366`

8. Medium-High: roadmap and stub endpoints are exposed inside the production API namespace.
   Evidence: `apps/api/urls.py:185-214`, `apps/api/roadmap_extended_views.py:37-47`, `apps/api/roadmap_extended_views.py:56-112`, `apps/api/roadmap_extended_views.py:133-243`
   Effect: API surface area overstates product maturity and complicates security, docs, and client integration boundaries.

9. Medium: compliance middleware mixes real controls with weak path bypasses and inline HTML strings.
   Evidence: `apps/compliance/middleware.py:253-271`, `apps/compliance/middleware.py:303-334`, `apps/compliance/middleware.py:432-444`

10. Medium: marketplace and blueprint surfaces exist structurally but are not activated as a functioning product.
    Evidence: marketplace counts in `00_scope_and_inventory.md`
    Effect: the UI can imply installability and governance where the operating loop is mostly empty.

## Contradictions That Matter

| Claimed state | Observed state |
|---|---|
| Runtime is the source of truth | Tenant behavior still merges direct school JSON and global solo settings |
| Navigation is governed | `portal_sidebar.html` and `portal_sidebar_items.py` still contain large hardcoded trees |
| No hardcoding | onboarding countries, fallback school code, grade approver defaults, page route detection, theme assets, and region defaults remain hardcoded |
| API is mature | `/api/roadmap/*` exposes many stubs and backlog placeholders |
| Migration cloud exists | only a narrow, semi-manual import flow is present; no recorded migration runs exist |
| Marketplace is installable | there are zero installations and zero tenant blueprints |

## Remediations Landed During This Review

1. Tenant context now reads the live `School.features` and `School.settings` JSON fields first, with legacy alias fallback.
   Files: `apps/tenancy/middleware.py`, `apps/tenancy/tests/test_tenant_context_middleware.py`

2. Passkey-only users now satisfy `_user_has_mfa()` consistently with MFA middleware behavior.
   Files: `apps/accounts/views_security.py`, `apps/accounts/tests/test_security_export_mfa.py`

3. Subject search is now school-scoped and no longer serializes a non-existent field.
   Files: `apps/api/search_api.py`, `apps/api/tests/test_search_api_tenant_scope.py`

## Bottom Line

This is a real system with substantial implementation depth, but the platform contract is overstated. The immediate priority is not adding more surfaces. The immediate priority is making the existing runtime, navigation, search, security, migration, and product surfaces internally consistent so the platform behaves like a single system instead of a runtime shell wrapped around legacy branches.
