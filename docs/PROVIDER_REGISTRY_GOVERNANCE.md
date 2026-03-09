# Provider registry and integration governance

**Purpose:** Single source of truth for integration types; runtime as authority; consistent use of catalog keys.

## Authority

- **Config schema and service keys:** `apps/siteconfig/integration_catalog.py` — `INTEGRATION_CATALOG` defines service_key → label, provider, category, config_schema, cost guardrails. New integration types must be added here first.
- **Runtime resolution:** `apps/platform_runtime/runtime_resolver.py` step 10 builds `IntegrationsContext` from `ServiceIntegration` (school, is_active). No ad-hoc integration tables; all tenant integrations flow through ServiceIntegration (or legacy Integration mapped via `integration_registry`).
- **Resolving a specific integration:** Call `resolve_active_integration(school, service_key)` from `apps/siteconfig/integration_registry.py`. The `service_key` should be a key from `INTEGRATION_CATALOG` (e.g. `whatsapp`, `stripe`, `push`, `badges`).

## Rules

1. **Catalog first:** To add a new integration type (e.g. SMS provider), add an entry to `INTEGRATION_CATALOG` with `config_schema`, then use that key in API Center and in `resolve_active_integration(school, key)`.
2. **No duplicate registries:** Do not create a second catalog or provider list; extend `INTEGRATION_CATALOG` and, if needed, `ServiceIntegration.ServiceType`.
3. **Runtime step 10:** Integrations context is populated only from ServiceIntegration (and legacy Integration via registry). No direct DB access in tenant app code for “list my integrations”; use runtime’s `runtime.integrations` or resolve by key.
4. **API Center:** Admin UI for tenant credentials should use `list_catalog_keys()` / `get_catalog_entry(service_key)` to drive forms and validation.

## References

- `apps/siteconfig/integration_catalog.py` — INTEGRATION_CATALOG, list_catalog_keys, get_catalog_entry
- `apps/siteconfig/integration_registry.py` — resolve_active_integration, IntegrationRecord
- `apps/platform_runtime/runtime_resolver.py` — _step10_integrations_marketplace
