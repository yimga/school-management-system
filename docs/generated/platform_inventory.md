# Platform Inventory

- Installed app modules: `41`
- Python files: `1744`
- HTML templates: `456`
- Markdown files: `793`
- Migration files: `585`
- Management commands: `137`
- `SiteSettings` refs: `1068`
- `get_solo()` refs: `212`
- `except Exception`: `741`
- `cursor.execute()`: `351`
- `csrf_exempt`: `79`
- `AllowAny`: `34`
- `print()`: `428`
- `gilead` matches: `484` across `110` files

## Public Endpoint Review

- Reviewed `csrf_exempt` files: `7`
- Reviewed `csrf_exempt` endpoints: `13`
- Reviewed `AllowAny` files: `1`
- Reviewed `AllowAny` occurrences: `2`

## SiteSettings Ownership

- `brand_experience`: `53` fields
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

- `apps/schools/marketing_views.py`: `3632` lines / `209838` bytes
- `apps/siteconfig/models.py`: `4527` lines / `176637` bytes
- `apps/schools/super_views.py`: `3040` lines / `130154` bytes
- `apps/accounts/views.py`: `2653` lines / `121002` bytes
- `apps/evals/views.py`: `2568` lines / `107834` bytes
- `apps/siteconfig/admin.py`: `2436` lines / `105463` bytes
- `apps/finance/views.py`: `2344` lines / `99544` bytes
- `apps/portal/views.py`: `2226` lines / `96646` bytes
- `apps/finance/models.py`: `2554` lines / `95611` bytes
- `apps/api/views_v1.py`: `1752` lines / `90549` bytes
- `apps/siteconfig/views.py`: `1794` lines / `75773` bytes
- `apps/finance/tasks.py`: `1604` lines / `74083` bytes

## Documentation Drift

- Legacy documented app count: `38`
- Actual installed app count: `41`
- Drift detected: `True`

