# Integrations & API Center (One Module)

Integration (plugin config) and API Center (governance, audit) are **one module**: a single model, one page, no redundancy.

## Current design

### Single model: `siteconfig.Integration`

- **Config:** name, slug, provider (email/sms/payments/analytics/other), config (JSON), enabled.
- **Governance:** category, rate_limit_per_min, ip_whitelist, allowed_scopes, secret_key_hash, last_call_at, health_status, pii_masking, school, created_at, updated_at.
- **Kill switch:** `enabled`. When Feature Control `enable_api_center` is on, `is_integration_allowed(integration)` returns `integration.enabled`.

### Audit: `apicenter.APIAuditLog`

- References `Integration` (FK). Each enable/disable in API Center writes a log entry (action, reason, changed_by, ip_address).

### One page

- **Integrations & API Center** (`/api-center/`): lists all Integrations; each card has Enable/Disable (with required reason) and link to Configuration Engine → Integrations for config. Audit log below.
- New integrations are added in **Configuration Engine → Integrations** (slug and optional governance fields). No separate “Register in API Center” step.

### Where it’s used

- **Finance:** `get_payment_integration_by_slug` / `get_payment_integration_by_method` return only integrations for which `is_integration_allowed(integration)` is True. Payment reminder email uses the email Integration only when allowed.
- **Portal:** Contact/help links (WhatsApp, other integrations) are shown only when `is_integration_allowed(integration)` is True.
- **Gating:** `apps.apicenter.gating.is_integration_allowed(integration)` — if `enable_api_center` is off, returns True; else returns `integration.enabled`.

### Other “integration” code

- **Communication:** `apps.communication.integrations` — Python classes (e.g. WhatsApp, Zoom); may use SiteSettings or env, not necessarily the Integration model.
- **Finance:** The live payment webhook uses `get_payment_integration_by_slug` (siteconfig Integration). `PaymentIntegration` in `finance/security.py` is a separate decorator path; the main registry is Integration.

### Feature Control & permission

- **Feature:** `enable_api_center` (backend). When off, API Center UI is hidden and gating is not applied (all enabled Integrations are allowed).
- **Permission:** `api_center.manage` (or roles ADMIN, IT_ADMIN, SUPERADMIN) to access the API Center page and toggle integrations.

## API v1: School list and primary_sector (Wedges 14–22)

External systems and analytics can filter and read school sector (education system type).

- **GET /api/v1/super/schools** — List active schools. Query: `?primary_sector=PUBLIC` (or any wedge 14–22 sector code). Response: `{ "schools": [ { "school_id", "name", "slug", "subdomain", "country_code", "primary_sector", "created_at" }, ... ], "total": N }`. Every school object includes `primary_sector`.
- **GET /api/v1/super/tenant-health** — Tenant health; query `?primary_sector=PUBLIC` filters; each tenant includes `primary_sector`.
- **GET /api/v1/super/usage** — Per-tenant usage; query `?primary_sector=PUBLIC` filters; each school includes `primary_sector`.
- **GET /api/v1/me/schools** — Schools the current user belongs to; each school includes `primary_sector`.

Sector codes (e.g. PUBLIC, GOVERNMENT_MINISTRY, NGO, INTERNATIONAL, MULTI_CAMPUS) are defined in `apps.registries.services.WEDGE_14_22_SECTOR_CODES`.
