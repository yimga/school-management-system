# Platform Inventory

- Installed app modules: `41`
- Python files: `1692`
- HTML templates: `451`
- Markdown files: `790`
- Migration files: `577`
- Management commands: `136`
- `SiteSettings` refs: `1046`
- `get_solo()` refs: `201`
- `except Exception`: `893`
- `cursor.execute()`: `352`
- `csrf_exempt`: `80`
- `AllowAny`: `34`
- `print()`: `426`
- `gilead` matches: `489` across `113` files

## Public Endpoint Review

- Reviewed `csrf_exempt` files: `7`
- Reviewed `csrf_exempt` endpoints: `13`
- Reviewed `AllowAny` files: `1`
- Reviewed `AllowAny` occurrences: `2`

## SiteSettings Ownership

- `brand_experience`: `41` fields
- `design_studio`: `1` fields
- `global_registries`: `3` fields
- `marketplace_integrations`: `1` fields
- `metadata_governance`: `111` fields
- `policies_rules`: `3` fields
- `preview_platform`: `2` fields
- `reports`: `4` fields
- `runtime_blueprints`: `13` fields
- `safe_platform_default`: `1` fields

## Successor Domain Imports Still Touching siteconfig

- `brand_experience`: `1` files
- `runtime_blueprints`: `1` files
- `plans_entitlements`: `1` files
- `global_registries`: `1` files
- `integrations_marketplace`: `1` files

## Largest Python Files

- `apps/schools/marketing_views.py`: `3632` lines / `209838` bytes
- `apps/siteconfig/models.py`: `4490` lines / `174805` bytes
- `apps/accounts/views.py`: `3371` lines / `155296` bytes
- `apps/schools/super_views.py`: `3202` lines / `137371` bytes
- `apps/siteconfig/admin.py`: `2508` lines / `108197` bytes
- `apps/portal/views.py`: `2427` lines / `107839` bytes
- `apps/evals/views.py`: `2554` lines / `107531` bytes
- `apps/finance/views.py`: `2370` lines / `102843` bytes
- `apps/api/views_v1.py`: `1903` lines / `99636` bytes
- `apps/finance/models.py`: `2554` lines / `95611` bytes
- `apps/siteconfig/views.py`: `1774` lines / `74154` bytes
- `apps/finance/tasks.py`: `1594` lines / `73613` bytes

## Documentation Drift

- Legacy documented app count: `38`
- Actual installed app count: `41`
- Drift detected: `True`

