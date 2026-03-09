# Siteconfig decomposition plan

**Purpose:** Reduce `apps/siteconfig` scope by moving theme, dashboard, workflow, region, billing, and tenant-config into dedicated platform layers. This doc defines the target boundaries and migration order.

## Current siteconfig modules (summary)

| Module | Role | Target layer |
|--------|------|--------------|
| `admin.py`, `admin_dashboard.py`, `unfold_dashboard.py` | Admin UI | Stay in siteconfig or move to `apps/admin_theme` |
| `context_processors.py` | Request context (SITE, theme, region) | Keep; inject from runtime/registries where possible |
| `models.py` | SiteSettings, ThemePack, RegionConfig, etc. | Split: control-plane only vs tenant defaults (see MODEL_TO_CANONICAL) |
| `dashboard_resolver.py`, `dashboard_registry.py`, `models_dashboard.py` | Dashboard packs/widgets | `apps/dashboard` (or dedicated `apps/dashboard_config`) |
| `workflow_resolver.py`, `workflow_registry.py`, `models_workflow.py`, `nuance_engine.py` | Workflow packs/engine | `apps/workflows` or keep under `apps/policies` |
| `tenant_config.py`, `system_morph.py` | Tenant config compilation | Platform tenant-config layer (e.g. `apps/platform_runtime` or `apps/tenant_config`) |
| `design_studio.py`, `views_school_theme.py` | Theme/design | `apps/theme` or `platform_runtime` branding |
| `billing_services.py` | Billing logic | `apps/billing` |
| `geoip_service.py` | Region lookup | `apps/registries` or locale layer |
| `currency.py` | Currency symbols | **Done:** moved to `apps/registries/currency.py`; siteconfig re-exports |
| `education_profile_engine.py`, `identifier_policy_service.py`, `student_id_service.py` | Education/ID | `apps/registries` or `apps/metadata` |
| `integration_catalog.py`, `migration_services.py` | Integrations/migration | Keep or move to `apps/marketplace` / migration app |
| `feature_toggles.py`, `preview_state.py` | Feature/preview | Keep or `platform_runtime` |

## Migration order

1. **Currency** — Moved to `apps/registries/currency.py`; `siteconfig.currency` re-exports (backward compatible).
2. **Dashboard** — Create `apps/dashboard_config` or extend `apps/dashboard`; move dashboard_resolver, dashboard_registry, models_dashboard; re-export from siteconfig during transition.
3. **Workflow** — Move workflow_resolver, workflow_registry, models_workflow to `apps/workflows` or under policies; re-export.
4. **Theme/design** — Move design_studio, views_school_theme to `apps/theme`; re-export.
5. **Billing** — Move billing_services to `apps/billing` (billing app may already exist).
6. **Region/geo** — Move geoip_service to registries or locale layer.
7. **Tenant config** — Move tenant_config, system_morph to platform_runtime or dedicated app; update resolver to import from new location.

## Rules

- Preserve backward compatibility: re-export from `siteconfig` during transition so existing imports keep working.
- Update `apps/siteconfig/apps.py` and remove moved code only after all callers use new paths (or keep re-exports indefinitely).
- Run full regression (smoke CI, tenant provisioning, dashboard, workflow, billing) after each move.

## References

- `docs/MODEL_TO_CANONICAL_MAPPING_REPORT.md`
- `docs/SCHOOL_FIELD_RESPONSIBILITY_MAP.md`
