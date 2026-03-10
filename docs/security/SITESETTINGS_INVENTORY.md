# SiteSettings / get_solo usage inventory

**Goal:** No direct `SiteSettings` / `get_solo` in tenant-facing flows; route behavior through runtime resolvers.

**Rule:** Tenant-facing views/serializers must use runtime resolver (e.g. `get_effective_site_settings(request=request)` or tenant-scoped helpers), not `SiteSettings.get_solo()`.

## Classification

- **Allowed global default** — Platform-wide, not tenant-specific (e.g. admin, migrations, seed).
- **Forbidden runtime bypass** — Tenant-facing; must use runtime resolver.
- **To-be-decomposed** — Move to registry, blueprint, policy, entitlement, or branding metadata.

## Inventory (representative; run full grep to complete)

| File | Function / context | Purpose | Classification |
|------|--------------------|---------|----------------|
| apps/siteconfig/models.py | SiteSettings.get_solo, cache | Singleton definition, cache refresh | Allowed (definition) |
| apps/siteconfig/admin.py | SiteSettingsAdmin | Admin CRUD for singleton | Allowed (admin) |
| apps/siteconfig/forms.py | SiteSettingsForm | Form for admin | Allowed (admin) |
| apps/siteconfig/views.py | theme_colors, brand import | Read/write for customizer | To-be-decomposed → branding resolver |
| apps/siteconfig/middleware/maintenance_mode.py | Maintenance check | Read maintenance_mode | Forbidden → runtime resolver |
| apps/siteconfig/tests/* | get_solo() | Tests | Allowed (test) |
| apps/finance/management/commands/seed_finance_defaults.py | get_solo() | Seed command | Allowed (bootstrap) |
| apps/finance/tasks.py | Feature flags, reminder channels | Tenant behavior | Forbidden → runtime resolver |
| apps/requests/tests/test_tasks.py | get_solo() | Test | Allowed (test) |
| apps/accounts/delegation.py | Role mapping from settings | Delegation workflow | To-be-decomposed → policy/registry |
| apps/reports/tests/*, apps/api/tests/* | get_solo() | Tests | Allowed (test) |
| apps/people/migrations/* | SiteSettings in migration | Data migration | Allowed (migration) |
| apps/platform_runtime/helpers.py | get_effective_site_settings | Runtime resolver (preferred) | Allowed (resolver) |

## Migration map

- **Platform default** — Non-tenant values (e.g. default grading keys) → PlatformDefaults or config module.
- **Registry** — Countries, calendars, grade scales → global_registries / metadata_catalog.
- **Blueprint** — Starter stack, composition → runtime_blueprints.
- **Policy** — Grading, attendance, approval rules → policies_rules.
- **Entitlement** — Plans, feature caps → plans_entitlements.
- **Branding** — Theme, logo, colors → brand_experience / runtime resolver.
- **Runtime-only** — Tenant-specific overrides → get_effective_site_settings(request=request) or tenant-scoped API.

## Next steps

1. Run: `grep -rn "get_solo\|SiteSettings" --include="*.py" apps/ config/` and add every remaining file to this table.
2. For each **Forbidden** or **To-be-decomposed**: open a ticket to switch to runtime resolver or new domain model.
3. Add CI/lint rule: flag new `SiteSettings.get_solo()` in `apps/*/views*.py`, `apps/*/serializers*.py`, `apps/*/tasks.py` (except siteconfig admin/forms).
