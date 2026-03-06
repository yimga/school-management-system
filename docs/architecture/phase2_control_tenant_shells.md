# Phase 2 — Control / Tenant / Public Shell Separation (12.2)

Verification that the platform separates **control plane**, **tenant runtime**, and **public** shells by host and URLconf. No tenant UX on control hosts; no control UX on tenant hosts.

## Implemented

### Host routing (`apps.schools.host_routing`)

- **public_host_kind(host)** returns: `"base"` | `"manager"` | `"api"` | `"docs"` | `"developer"` | `"verify"` | `"support"` | `"local"` | `None` (tenant).
- **Reserved public subdomains:** www, admin, verify, support, api, docs, manager, developer.
- **Local hosts:** localhost, 127.0.0.1, manager.localhost, developer.localhost, etc.

### URLconf switching (`apps.schools.middleware.UrlConfSwitcherMiddleware`)

| Host kind   | request.urlconf       | Shell        |
|------------|------------------------|--------------|
| local      | config.urls            | Full (dev)   |
| manager    | config.manager_urls    | Control      |
| api        | config.api_urls        | API          |
| docs       | config.docs_urls       | Docs         |
| base       | config.public_urls     | Public       |
| (tenant)   | config.tenant_urls     | Tenant       |

- **Control shell:** `config/manager_urls.py` — manager home, `/super/` (super_urls), siteconfig, api-center, ops/incidents, health, billing webhooks, observability. No tenant app URLs (portal, academics, evals, etc.) on manager host.
- **Tenant shell:** `config/tenant_urls.py` — backend, portal, academics, finance, evals, reports, communication, etc. `/super/` is not mounted on tenant urlconf; if a tenant host ever serves a path starting with `/super/`, `ReservedPublicHostAccessMiddleware` redirects to manager host.
- **Public shell:** `config/public_urls.py` — marketing, signup, discover, verify, support. No tenant data.

### Separation guarantees

- **24.7:** Superadmin UX is on manager host and `/super/`; tenant UX is on tenant subdomains/custom domains. Structurally and visually separate.
- **No URL fall-through:** Tenant domain cannot serve `/super/` (redirect to manager). Manager host does not serve tenant app routes.

## References

- Checklist: Section 12.2 (Phase 2), 24.7 (superadmin separate).
- `apps/schools/host_routing.py`, `apps/schools/middleware.py` (UrlConfSwitcherMiddleware, ReservedPublicHostAccessMiddleware).
- `config/manager_urls.py`, `config/tenant_urls.py`, `config/public_urls.py`.
- `docs/ADMIN_AND_TENANT_URLS.md`, `docs/ACCESS_POINTS.md`.
