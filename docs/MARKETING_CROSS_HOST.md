# Marketing and cross-host link behavior

## Rule

- **Marketing content is served on the apex/public host** (e.g. `runmycampus.com` or the domain set in `MULTI_TENANT_BASE_DOMAIN`). The public urlconf (`config.public_urls`) is used when the request host is identified as the public/apex host.
- **Tenant** (e.g. `school.runmycampus.com`) and **manager** (e.g. `manager.runmycampus.com`) **do not serve marketing routes**. They use their own urlconfs (tenant_urls, manager_urls).
- **Links from tenant and manager to marketing** (Pricing, Status, RunMyCampus home, Trust Center, Signup, etc.) must point to the **canonical marketing base URL** so they open on the apex domain, not on the current host.

## Implementation

- **Canonical base domain:** `apps.schools.host_routing.get_canonical_base_domain()` returns the single source of truth (from `MULTI_TENANT_BASE_DOMAIN` or default `runmycampus.com`).
- **Template context:** The context processor `apps.schools.context_processors.marketing_base_url` adds **`MARKETING_BASE_URL`** to every request (e.g. `https://runmycampus.com`). Use it in tenant and manager templates for any link that should open the marketing site.
- **Where it’s used:**
  - **Dashboard footer** (`templates/components/dashboard_footer.html`): “Platform Status” links to `{{ MARKETING_BASE_URL }}/status/`, and the footer meta includes “RunMyCampus” and “Pricing” linking to `{{ MARKETING_BASE_URL }}/` and `{{ MARKETING_BASE_URL }}/pricing/`.
  - **Docs landing** (`templates/schools/docs_landing.html`): “Back to Marketing” uses `{{ MARKETING_BASE_URL }}/` when available.

## Optional: Status on manager/tenant

On **tenant** and **manager** hosts, `/status/` is the app health endpoint. On the **apex (public)** host, `/status/` is the **marketing trust/uptime page**; for health checks on the apex host use **`/health/`** or **`/healthz/`**. If you want manager or tenant to show a “Platform status” link, it should point to the apex uptime page: `{{ MARKETING_BASE_URL }}/status/` The path `/uptime/` is an alias for the same page.

## Tests

Add or extend tests to verify:

1. Links from manager/tenant templates that are intended to reach marketing use `MARKETING_BASE_URL` (or render to a URL on the canonical base domain).
2. Resolving `MARKETING_BASE_URL` in a request context returns the expected scheme and host (e.g. `https://runmycampus.com` when `MULTI_TENANT_BASE_DOMAIN` is set or default).

## Exceptions

- No marketing routes are served on tenant or manager except as above (links only). If product requirements later say that manager or tenant should **serve** a specific page (e.g. a minimal Status page that redirects to apex), implement that as a redirect to `{{ MARKETING_BASE_URL }}/status/` (or the appropriate path) to avoid duplication.
