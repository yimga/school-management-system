# Data residency and compliance

This document summarizes data handling for multi-tenant deployments (Option B+C).

## Data location

- **Database**: All tenant data is stored in the same database. Data resides in the region of the deployment (e.g. the cloud region where the app and DB run). No automatic geo-replication of tenant data is performed by the application.
- **HTTPS**: All traffic is expected over TLS (HTTPS). Configure your reverse proxy (e.g. Caddy, Cloudflare, or load balancer) to terminate SSL.

## Encryption

- **In transit**: Use HTTPS only. TLS 1.2+ is recommended.
- **At rest**: Use your database provider’s encryption-at-rest (e.g. PostgreSQL TDE or managed DB encryption). No application-level encryption of stored data is required for baseline compliance.

## Tenant isolation

- **Row-Level Security (RLS)**: On PostgreSQL, RLS is enabled for tenant-scoped tables. The middleware sets `app.current_school_id` per request so that queries only see rows for the current school.
- **Application scoping**: All tenant-scoped views and APIs filter by `request.school` (or equivalent) so that users cannot access another school’s data.

## Custom domains and whitelabel

- Schools can set a **custom domain** (e.g. `portal.school.edu`). The platform resolves the school from the request host (subdomain or custom domain).
- DNS verification: use the `verify_custom_domains` management command to set `custom_domain_verified` after the school adds the required CNAME.

## Retention and deletion

- Define retention and deletion policies in your operational runbooks. The application does not auto-delete tenant data; use admin or scripts to purge when required.
