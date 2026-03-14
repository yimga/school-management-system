# Platform Inventory

- Installed app modules: `41`
- Python files: `1818`
- HTML templates: `461`
- Markdown files: `841`
- Migration files: `594`
- Management commands: `139`
- `SiteSettings` refs: `1073`
- `get_solo()` refs: `178`
- `except Exception`: `399`
- `cursor.execute()`: `349`
- `csrf_exempt`: `97`
- `AllowAny`: `52`
- `print()`: `451`
- `gilead` matches: `657` across `128` files

## Public Endpoint Review

- Reviewed `csrf_exempt` files: `7`
- Reviewed `csrf_exempt` endpoints: `13`
- Reviewed `AllowAny` files: `1`
- Reviewed `AllowAny` occurrences: `2`

## SiteSettings Ownership

- `brand_experience`: `54` fields
- `delete`: `1` fields
- `design_studio`: `1` fields
- `documents`: `1` fields
- `global_registries`: `6` fields
- `marketplace_integrations`: `9` fields
- `policies_rules`: `80` fields
- `preview_platform`: `3` fields
- `reports`: `10` fields
- `runtime_blueprints`: `14` fields
- `safe_platform_default`: `2` fields

## Successor Domain Imports Still Touching siteconfig

- `brand_experience`: `1` files
- `runtime_blueprints`: `1` files
- `plans_entitlements`: `1` files
- `global_registries`: `1` files
- `integrations_marketplace`: `1` files

## Largest Python Files

- `apps/schools/marketing_views.py`: `3659` lines / `212639` bytes
- `apps/schools/super_views.py`: `2797` lines / `121007` bytes
- `apps/evals/views.py`: `2564` lines / `107567` bytes
- `apps/siteconfig/admin.py`: `2542` lines / `106877` bytes
- `apps/accounts/views.py`: `2331` lines / `103900` bytes
- `apps/finance/views.py`: `2373` lines / `100201` bytes
- `apps/portal/views.py`: `2216` lines / `96105` bytes
- `apps/finance/models.py`: `2556` lines / `95914` bytes
- `apps/siteconfig/models.py`: `2378` lines / `95888` bytes
- `apps/api/views_v1.py`: `1740` lines / `90067` bytes
- `apps/siteconfig/views.py`: `1916` lines / `81212` bytes
- `apps/finance/tasks.py`: `1775` lines / `80075` bytes

## Documentation Drift

- Legacy documented app count: `38`
- Actual installed app count: `41`
- Drift detected: `True`

