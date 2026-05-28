# Platform Inventory

- Installed app modules: `52`
- Python files: `5395`
- HTML templates: `1511`
- Markdown files: `1562`
- Migration files: `927`
- Management commands: `273` (full list in JSON key `management_commands_list`)
- `SiteSettings` refs (gross scan): `2411`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations): `187`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations+tests): `141`
- `get_solo()` refs: `212`
- `except Exception`: `1796`
- `cursor.execute()` (gross): `396`
- `cursor.execute()` (`apps`+`config` `.py`, excl. migrations): `40`
- `csrf_exempt` (substring, gross): `504`
- `csrf_exempt` decorator lines (`apps`+`config`, excl. migrations): `54`
- `AllowAny`: `173`
- `print()` (gross all `.py`): `3068`
- `print()` (`apps` product paths): `0`; `scripts/`: `2891`
- `gilead` matches (gross corpus): `16829` across `227` files
- `gilead` line hits (`apps`+`templates`+`config`, excl. migrations+tests+`management/commands`): `0`

Gross totals include migrations and broad file pools; use **scoped** lines around SQL/SiteSettings/Tenant gravity for trend tracking (see SOT §0 *Structural remediation stack*).
- Scoped-gravity **history** (last writes): `scripts/generated/scoped_gravity_trend.json` (updated with `generate_platform_inventory.py --write`; excluded from gross `gilead` JSON scan).

## Management Commands (full list)

Total: `273` commands. First 25 by app/command:

- `academics` / `export_certification_pack` — `apps/academics/management/commands/export_certification_pack.py`
- `academics` / `fix_term_positions` — `apps/academics/management/commands/fix_term_positions.py`
- `academics` / `import_curriculum_nodes` — `apps/academics/management/commands/import_curriculum_nodes.py`
- `academics` / `run_auto_promotion` — `apps/academics/management/commands/run_auto_promotion.py`
- `academics` / `seed_buea_synthetic` — `apps/academics/management/commands/seed_buea_synthetic.py`
- `academics` / `seed_demo` — `apps/academics/management/commands/seed_demo.py`
- `academics` / `seed_testdata_2425` — `apps/academics/management/commands/seed_testdata_2425.py`
- `academics` / `solve_timetable` — `apps/academics/management/commands/solve_timetable.py`
- `accounts` / `backfill_user_roles` — `apps/accounts/management/commands/backfill_user_roles.py`
- `accounts` / `check_roles` — `apps/accounts/management/commands/check_roles.py`
- `accounts` / `create_teacher_parent_accounts` — `apps/accounts/management/commands/create_teacher_parent_accounts.py`
- `accounts` / `ensure_default_tenant_admin` — `apps/accounts/management/commands/ensure_default_tenant_admin.py`
- `accounts` / `ensure_platform_operator_profiles` — `apps/accounts/management/commands/ensure_platform_operator_profiles.py`
- `accounts` / `ensure_superadmin` — `apps/accounts/management/commands/ensure_superadmin.py`
- `accounts` / `ensure_superuser` — `apps/accounts/management/commands/ensure_superuser.py`
- `accounts` / `list_expired_temporary_grants` — `apps/accounts/management/commands/list_expired_temporary_grants.py`
- `accounts` / `refresh_saml_idp_metadata` — `apps/accounts/management/commands/refresh_saml_idp_metadata.py`
- `accounts` / `rotate_encryption_keys` — `apps/accounts/management/commands/rotate_encryption_keys.py`
- `accounts` / `security_log_retention` — `apps/accounts/management/commands/security_log_retention.py`
- `accounts` / `seed_render_users` — `apps/accounts/management/commands/seed_render_users.py`
- `accounts` / `seed_tenant_identity_demo` — `apps/accounts/management/commands/seed_tenant_identity_demo.py`
- `accounts` / `sync_rebac_tuples` — `apps/accounts/management/commands/sync_rebac_tuples.py`
- `analytics` / `ai_narrate_risk_digest` — `apps/analytics/management/commands/ai_narrate_risk_digest.py`
- `analytics` / `bootstrap_at_risk_registry` — `apps/analytics/management/commands/bootstrap_at_risk_registry.py`
- `analytics` / `build_student_embeddings` — `apps/analytics/management/commands/build_student_embeddings.py`
- … and 248 more (see `platform_inventory.json` key `management_commands_list`).

## Public Endpoint Review

- Reviewed `csrf_exempt` files: `23`
- Reviewed `csrf_exempt` endpoints: `54`
- Reviewed `AllowAny` files: `4`
- Reviewed `AllowAny` occurrences: `10`

## SiteSettings Ownership

- `brand_experience`: `1` fields
- `delete`: `1` fields
- `metadata_governance`: `2` fields
- `safe_platform_default`: `1` fields

## Successor Domain Imports Still Touching siteconfig

- `brand_experience`: `10` files
- `runtime_blueprints`: `1` files
- `plans_entitlements`: `1` files
- `global_registries`: `1` files
- `integrations_marketplace`: `18` files

## Largest Python Files

- `apps/siteconfig/forms_cockpit.py`: `5086` lines / `206345` bytes
- `apps/schools/marketing_views.py`: `4123` lines / `164862` bytes
- `config/settings.py`: `3158` lines / `151532` bytes
- `apps/schools/marketing_page_definitions.py`: `3056` lines / `143830` bytes
- `apps/accounts/views.py`: `3557` lines / `141001` bytes
- `apps/evals/views.py`: `3416` lines / `131340` bytes
- `apps/api/views_v1.py`: `2905` lines / `119916` bytes
- `apps/migration_cloud/views.py`: `2645` lines / `112695` bytes
- `apps/siteconfig/_seed_country_localization.py`: `1920` lines / `110379` bytes
- `scripts/_batch_1489_generate_edos_artifacts.py`: `1958` lines / `108724` bytes
- `apps/siteconfig/views.py`: `2812` lines / `106610` bytes
- `apps/finance/models.py`: `3038` lines / `106422` bytes

## Documentation Drift

- Legacy documented app count: `52`
- Actual installed app count: `52`
- Drift detected: `False`

