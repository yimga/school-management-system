# Platform engines (product layer)

Migration Cloud, Marketplace, Integrations/Provider Registry, and Observability are first-class product layers. They are governed, versioned, and observable—not ad-hoc tools.

## Migration Cloud

- **Product layer:** Tenant migration, data validation, run orchestration, rollback. See `schools/super_migration_cloud.html`, migration services, and tenant provisioning.
- **Governance:** Migration runs and issues are auditable; no direct tenant data exposure without scope.

## Marketplace

- **Product layer:** App catalog, installation, lifecycle, capability registry, tenant-scoped consent. See `apps.marketplace`, templates under `marketplace/`.
- **Governance:** App versions, compatibility matrix, health checks; installed apps feed `request.tenant_runtime.marketplace`.

## Integrations / Provider Registry

- **Runtime:** Resolved in `platform_runtime.runtime_resolver` (integrations context: payment_provider, messaging_provider, etc.) and used by finance/communication.
- **Failover:** Provider selection and failover belong in a central registry/resolver, not per-app branching.

## Observability

- **Product layer:** Health scoring, incidents, pulse, tenant vitality. See `apps.observability`, control plane pulse/tenant health/analytics.
- **Governance:** Observability middleware and metrics; no PII in logs without policy.

## References

- ARCHITECTURE_LAWS.md (Law 6: versioned, auditable; Law 8: observable)
- apps/platform_runtime/contracts.py (IntegrationsContext, MarketplaceContext)
- apps/schools/control_plane_nav.py (Migration, Marketplace, Observability nav)
