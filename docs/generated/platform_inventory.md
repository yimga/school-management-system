# Platform Inventory

- Installed app modules: `55`
- Python files: `8702`
- HTML templates: `2101`
- Markdown files: `1888`
- Migration files: `1281`
- Management commands: `400` (full list in JSON key `management_commands_list`)
- `SiteSettings` refs (gross scan): `2590`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations): `237`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations+tests): `165`
- `get_solo()` refs: `213`
- `except Exception`: `3981`
- `cursor.execute()` (gross): `718`
- `cursor.execute()` (`apps`+`config` `.py`, excl. migrations): `70`
- `csrf_exempt` (substring, gross): `767`
- `csrf_exempt` decorator lines (`apps`+`config`, excl. migrations): `115`
- `AllowAny`: `166`
- `print()` (gross all `.py`): `5609`
- `print()` (`apps` product paths): `0`; `scripts/`: `5386`
- `gilead` matches (gross corpus): `42084` across `466` files
- `gilead` line hits (`apps`+`templates`+`config`, excl. migrations+tests+`management/commands`): `0`

Gross totals include migrations and broad file pools; use **scoped** lines around SQL/SiteSettings/Tenant gravity for trend tracking (see SOT §0 *Structural remediation stack*).
- Scoped-gravity **history** (last writes): `scripts/generated/scoped_gravity_trend.json` (updated with `generate_platform_inventory.py --write`; excluded from gross `gilead` JSON scan).

## Management Commands (full list)

Total: `400` commands. First 25 by app/command:

- `academics` / `export_certification_pack` — `apps/academics/management/commands/export_certification_pack.py`
- `academics` / `export_country_catalog_template` — `apps/academics/management/commands/export_country_catalog_template.py`
- `academics` / `fix_term_positions` — `apps/academics/management/commands/fix_term_positions.py`
- `academics` / `import_country_official_catalog` — `apps/academics/management/commands/import_country_official_catalog.py`
- `academics` / `import_curriculum_nodes` — `apps/academics/management/commands/import_curriculum_nodes.py`
- `academics` / `run_auto_promotion` — `apps/academics/management/commands/run_auto_promotion.py`
- `academics` / `seed_buea_synthetic` — `apps/academics/management/commands/seed_buea_synthetic.py`
- `academics` / `seed_demo` — `apps/academics/management/commands/seed_demo.py`
- `academics` / `seed_testdata_2425` — `apps/academics/management/commands/seed_testdata_2425.py`
- `academics` / `solve_timetable` — `apps/academics/management/commands/solve_timetable.py`
- `accounts` / `backfill_guardian_memberships` — `apps/accounts/management/commands/backfill_guardian_memberships.py`
- `accounts` / `backfill_user_roles` — `apps/accounts/management/commands/backfill_user_roles.py`
- `accounts` / `check_rebac_enforcement_readiness` — `apps/accounts/management/commands/check_rebac_enforcement_readiness.py`
- `accounts` / `check_roles` — `apps/accounts/management/commands/check_roles.py`
- `accounts` / `create_teacher_parent_accounts` — `apps/accounts/management/commands/create_teacher_parent_accounts.py`
- `accounts` / `ensure_default_tenant_admin` — `apps/accounts/management/commands/ensure_default_tenant_admin.py`
- `accounts` / `ensure_platform_operator_profiles` — `apps/accounts/management/commands/ensure_platform_operator_profiles.py`
- `accounts` / `ensure_superadmin` — `apps/accounts/management/commands/ensure_superadmin.py`
- `accounts` / `ensure_superuser` — `apps/accounts/management/commands/ensure_superuser.py`
- `accounts` / `fix_tenant_login` — `apps/accounts/management/commands/fix_tenant_login.py`
- `accounts` / `invite_school_owner` — `apps/accounts/management/commands/invite_school_owner.py`
- `accounts` / `list_expired_temporary_grants` — `apps/accounts/management/commands/list_expired_temporary_grants.py`
- `accounts` / `promote_superadmin` — `apps/accounts/management/commands/promote_superadmin.py`
- `accounts` / `recover_unactivated_owners` — `apps/accounts/management/commands/recover_unactivated_owners.py`
- `accounts` / `refresh_saml_idp_metadata` — `apps/accounts/management/commands/refresh_saml_idp_metadata.py`
- … and 375 more (see `platform_inventory.json` key `management_commands_list`).

## Public Endpoint Review

- Reviewed `csrf_exempt` files: `39`
- Reviewed `csrf_exempt` endpoints: `115`
- Reviewed `AllowAny` files: `5`
- Reviewed `AllowAny` occurrences: `13`

## SiteSettings Ownership

- `delete`: `1` fields
- `safe_platform_default`: `1` fields

## Successor Domain Imports Still Touching siteconfig

- `brand_experience`: `11` files
- `runtime_blueprints`: `1` files
- `plans_entitlements`: `1` files
- `global_registries`: `1` files
- `integrations_marketplace`: `19` files

## Largest Python Files

- `apps/siteconfig/_seed_country_localization.py`: `16897` lines / `1225749` bytes
- `apps/siteconfig/forms_cockpit.py`: `6416` lines / `257782` bytes
- `config/settings.py`: `4735` lines / `242768` bytes
- `apps/accounts/views.py`: `5003` lines / `206143` bytes
- `apps/schools/marketing_views.py`: `4217` lines / `169799` bytes
- `apps/migration_cloud/views.py`: `3659` lines / `159377` bytes
- `apps/api/saml.py`: `3487` lines / `147039` bytes
- `apps/schools/marketing_page_definitions.py`: `3056` lines / `143830` bytes
- `apps/evals/views.py`: `3639` lines / `141015` bytes
- `apps/api/oneroster_results.py`: `3418` lines / `139254` bytes
- `apps/schools/signup_views.py`: `2999` lines / `125707` bytes
- `apps/finance/models.py`: `3407` lines / `123979` bytes

## Documentation Drift

- Legacy documented app count: `55`
- Actual installed app count: `55`
- Drift detected: `False`

