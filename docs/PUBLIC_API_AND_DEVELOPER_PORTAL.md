# Public API and Developer Portal (Plan 4.10 / 4.11)

RunMyCampus exposes **versioned APIs** and integration points for partners and schools. This doc is the single reference for auth, rate limiting, and endpoints; the marketing site links to it from the Developer Portal page (`/developers/`).

## 1. API access and authentication

- **Tenant APIs:** Authenticate per tenant (school) using session auth or API keys scoped to the tenant. Use the tenant subdomain (e.g. `school.runmycampus.com`) for tenant-scoped calls.
- **Public / marketing APIs:** Some read-only endpoints (e.g. health, domain check) are on the apex domain without tenant context.
- **OAuth / API keys:** Document in your deployment how API keys are issued (e.g. from Site Settings or super-admin). Keys are scoped to a tenant; never use a single key across tenants.

## 2. Rate limiting

- **Per-IP and per-tenant:** Apply rate limits to avoid abuse and noisy neighbors. Return **429 Too Many Requests** with **Retry-After** when limits are exceeded.
- **Recommended:** e.g. 100–200 requests per hour per IP for unauthenticated public endpoints; higher limits per tenant for authenticated API usage. Configure in your reverse proxy or Django middleware.

## 3. Versioned endpoints

- **Base path:** Use a version prefix such as `/api/v1/` for stable, versioned APIs. Avoid breaking changes within a major version; introduce new versions for breaking changes.
- **OpenAPI:** Maintain an OpenAPI (Swagger) spec for the main REST API and link it from the Developer Portal page so partners can discover endpoints and payloads.

## 4. Integrations (LTI, OneRoster, webhooks)

- **LTI 1.3:** Launch and service endpoints are under `/lti/` (launch, line items, scores, memberships, deep linking). See LTI docs in the codebase.
- **OneRoster / other standards:** Document and implement in phases; align with Interoperability (Plan 4.10).
- **Webhooks:** Outbound events (e.g. enrollment, payment) can be delivered to subscriber URLs; configure per tenant and respect rate limits and retries.

## 5. Developer Portal page

- **Marketing route:** `/developers/` — links to this doc, OpenAPI spec (when available), and high-level sections (API access, rate limiting, integrations). No duplicate “single plan” doc; this file is the technical reference for the Public API and Developer Portal.
