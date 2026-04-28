# Incident response policy (product-aligned)

## Detection

- Operator-facing: platform incidents and support ticket flows (`apps/schools` / observability modules as configured).
- Application errors: structured logging; review `docs/deployment/` for host-specific logging guidance.

## Classification (internal)

1. **Availability** — full or partial outage.
2. **Integrity** — suspected data corruption or unauthorized change.
3. **Confidentiality** — suspected data exposure across tenants.

## Response (high level)

1. Preserve logs and request IDs.
2. Isolate: disable feature flags where available (`siteconfig` feature control).
3. Communicate via customer support channels (process outside repo).

## Evidence in repo

- Incident-related URLs and models under `apps/` (search `PlatformIncident`).
- Deployment rollback notes under `docs/deployment/`.

This file does **not** replace a company-wide IR plan or on-call roster.
