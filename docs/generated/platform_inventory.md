# Platform Inventory

- Installed app modules: `55`
- Python files: `7711`
- HTML templates: `2001`
- Markdown files: `1832`
- Migration files: `1185`
- Management commands: `342` (full list in JSON key `management_commands_list`)
- `SiteSettings` refs (gross scan): `2505`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations): `217`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations+tests): `158`
- `get_solo()` refs: `213`
- `except Exception`: `3271`
- `cursor.execute()` (gross): `606`
- `cursor.execute()` (`apps`+`config` `.py`, excl. migrations): `58`
- `csrf_exempt` (substring, gross): `755`
- `csrf_exempt` decorator lines (`apps`+`config`, excl. migrations): `113`
- `AllowAny`: `161`
- `print()` (gross all `.py`): `5128`
- `print()` (`apps` product paths): `0`; `scripts/`: `4915`
- `gilead` matches (gross corpus): `17103` across `254` files
- `gilead` line hits (`apps`+`templates`+`config`, excl. migrations+tests+`management/commands`): `0`

Gross totals include migrations and broad file pools; use **scoped** lines around SQL/SiteSettings/Tenant gravity for trend tracking (see SOT §0 *Structural remediation stack*).
- Scoped-gravity **history** (last writes): `scripts/generated/scoped_gravity_trend.json` (updated with `generate_platform_inventory.py --write`; excluded from gross `gilead` JSON scan).

## Management Commands (full list)

Total: `342` commands. First 25 by app/command:

- `academics` / `export_certification_pack` — `apps/academics/management/commands/export_certification_pack.py`
- `academics` / `fix_term_positions` — `apps/academics/management/commands/fix_term_positions.py`
- `academics` / `import_curriculum_nodes` — `apps/academics/management/commands/import_curriculum_nodes.py`
- `academics` / `run_auto_promotion` — `apps/academics/management/commands/run_auto_promotion.py`
- `academics` / `seed_buea_synthetic` — `apps/academics/management/commands/seed_buea_synthetic.py`
- `academics` / `seed_demo` — `apps/academics/management/commands/seed_demo.py`
- `academics` / `seed_testdata_2425` — `apps/academics/management/commands/seed_testdata_2425.py`
- `academics` / `solve_timetable` — `apps/academics/management/commands/solve_timetable.py`
- `accounts` / `backfill_user_roles` — `apps/accounts/management/commands/backfill_user_roles.py`
- `accounts` / `check_rebac_enforcement_readiness` — `apps/accounts/management/commands/check_rebac_enforcement_readiness.py`
- `accounts` / `check_roles` — `apps/accounts/management/commands/check_roles.py`
- `accounts` / `create_teacher_parent_accounts` — `apps/accounts/management/commands/create_teacher_parent_accounts.py`
- `accounts` / `ensure_default_tenant_admin` — `apps/accounts/management/commands/ensure_default_tenant_admin.py`
- `accounts` / `ensure_platform_operator_profiles` — `apps/accounts/management/commands/ensure_platform_operator_profiles.py`
- `accounts` / `ensure_superadmin` — `apps/accounts/management/commands/ensure_superadmin.py`
- `accounts` / `ensure_superuser` — `apps/accounts/management/commands/ensure_superuser.py`
- `accounts` / `list_expired_temporary_grants` — `apps/accounts/management/commands/list_expired_temporary_grants.py`
- `accounts` / `promote_superadmin` — `apps/accounts/management/commands/promote_superadmin.py`
- `accounts` / `refresh_saml_idp_metadata` — `apps/accounts/management/commands/refresh_saml_idp_metadata.py`
- `accounts` / `reset_user_mfa` — `apps/accounts/management/commands/reset_user_mfa.py`
- `accounts` / `rotate_encryption_keys` — `apps/accounts/management/commands/rotate_encryption_keys.py`
- `accounts` / `security_log_retention` — `apps/accounts/management/commands/security_log_retention.py`
- `accounts` / `seed_render_users` — `apps/accounts/management/commands/seed_render_users.py`
- `accounts` / `seed_tenant_identity_demo` — `apps/accounts/management/commands/seed_tenant_identity_demo.py`
- `accounts` / `sync_rebac_tuples` — `apps/accounts/management/commands/sync_rebac_tuples.py`
- … and 317 more (see `platform_inventory.json` key `management_commands_list`).

## Public Endpoint Review

- Reviewed `csrf_exempt` files: `38`
- Reviewed `csrf_exempt` endpoints: `113`
- Reviewed `AllowAny` files: `4`
- Reviewed `AllowAny` occurrences: `10`

## SiteSettings Ownership

- `delete`: `1` fields
- `safe_platform_default`: `1` fields

## Successor Domain Imports Still Touching siteconfig

- `brand_experience`: `10` files
- `runtime_blueprints`: `1` files
- `plans_entitlements`: `1` files
- `global_registries`: `1` files
- `integrations_marketplace`: `18` files

## Largest Python Files

- `apps/siteconfig/_seed_country_localization.py`: `16897` lines / `1225749` bytes
- `apps/siteconfig/forms_cockpit.py`: `6335` lines / `254532` bytes
- `config/settings.py`: `4239` lines / `213312` bytes
- `apps/accounts/views.py`: `4711` lines / `191001` bytes
- `apps/schools/marketing_views.py`: `4207` lines / `169135` bytes
- `apps/api/saml.py`: `3487` lines / `147039` bytes
- `apps/schools/marketing_page_definitions.py`: `3056` lines / `143830` bytes
- `apps/evals/views.py`: `3618` lines / `140257` bytes
- `apps/api/oneroster_results.py`: `3418` lines / `139254` bytes
- `apps/migration_cloud/views.py`: `2921` lines / `126469` bytes
- `apps/api/views_v1.py`: `3006` lines / `123722` bytes
- `apps/finance/models.py`: `3337` lines / `120762` bytes

## Documentation Drift

- Legacy documented app count: `55`
- Actual installed app count: `55`
- Drift detected: `False`

