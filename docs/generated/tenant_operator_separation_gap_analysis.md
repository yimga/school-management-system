# Tenant Operator Separation Gap Analysis

Status: **PASS**

Rule: tenant day-to-day frontend, tenant configuration backend, and operator control plane are separate surfaces. Tenant scope must never resolve into operator scope.

## Closed Gaps
- Tenant-host /super/ no longer redirects to manager host.
- Tenant Configuration Control Center suppresses operator links.
- Tenant command palette suppresses /super/ and /admin/ actions.
- Shared Studio/siteconfig templates guard operator URL tags by manager scope.
- Root /admin/ dispatcher fails closed for unresolved tenant-like hosts.
- Studio deep links fail closed for super:/admin: unless explicitly manager-scoped.
- Tenant and platform admin sites resolve through distinct URLconfs and registries.

## Watch Gaps Requiring Separate Proof
- PostgreSQL/RLS data-plane proof: UNVERIFIED_BY_THIS_AUDIT - This command proves route/link/admin separation, not row-level SQL policy behavior.
- Object storage and media prefixes: UNVERIFIED_BY_THIS_AUDIT - Needs storage-provider fixture or integration audit to prove tenant prefix isolation.
- Async jobs and cache tenant context: UNVERIFIED_BY_THIS_AUDIT - Needs task queue/cache key audit to prove tenant context propagation outside requests.
- All API serializers/querysets: UNVERIFIED_BY_THIS_AUDIT - Needs queryset/RLS scanner plus endpoint smoke matrix by tenant membership.

## World-Class Operating Pattern
- Resolve tenant context first, then authorize every resource with that tenant context.
- Keep tenant admin/configuration separate from platform/operator administration.
- Use least-privilege scopes for app/platform access and make expanded access explicit.
- Treat routes, command palettes, deep links, background jobs, storage prefixes, and API querysets as security boundaries.

## Reference Patterns
- AWS: Separate authentication from tenant isolation; enforce tenant-aware authorization at API enforcement points. (https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-api-access-authorization/introduction.html)
- Salesforce: Use tenant/org identifiers and metadata-driven runtime separation so each tenant customizes independently. (https://architect.salesforce.com/docs/architect/fundamentals/guide/platform-multitenant-architecture.html)
- Shopify: Use explicit access scopes and separate admin/storefront/customer access classes. (https://shopify.dev/docs/api/usage/access-scopes)
