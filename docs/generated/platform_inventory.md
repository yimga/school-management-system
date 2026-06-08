# Platform Inventory

- Installed app modules: `54`
- Python files: `6359`
- HTML templates: `1656`
- Markdown files: `1612`
- Migration files: `1001`
- Management commands: `298` (full list in JSON key `management_commands_list`)
- `SiteSettings` refs (gross scan): `2470`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations): `214`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations+tests): `161`
- `get_solo()` refs: `213`
- `except Exception`: `2581`
- `cursor.execute()` (gross): `414`
- `cursor.execute()` (`apps`+`config` `.py`, excl. migrations): `45`
- `csrf_exempt` (substring, gross): `682`
- `csrf_exempt` decorator lines (`apps`+`config`, excl. migrations): `112`
- `AllowAny`: `173`
- `print()` (gross all `.py`): `4339`
- `print()` (`apps` product paths): `0`; `scripts/`: `4152`
- `gilead` matches (gross corpus): `16847` across `237` files
- `gilead` line hits (`apps`+`templates`+`config`, excl. migrations+tests+`management/commands`): `0`

Gross totals include migrations and broad file pools; use **scoped** lines around SQL/SiteSettings/Tenant gravity for trend tracking (see SOT §0 *Structural remediation stack*).
- Scoped-gravity **history** (last writes): `scripts/generated/scoped_gravity_trend.json` (updated with `generate_platform_inventory.py --write`; excluded from gross `gilead` JSON scan).

## Management Commands (full list)

Total: `298` commands. First 25 by app/command:

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
- … and 273 more (see `platform_inventory.json` key `management_commands_list`).

## Public Endpoint Review

- Reviewed `csrf_exempt` files: `37`
- Reviewed `csrf_exempt` endpoints: `112`
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
- `apps/siteconfig/forms_cockpit.py`: `5127` lines / `208363` bytes
- `config/settings.py`: `3622` lines / `176381` bytes
- `apps/schools/marketing_views.py`: `4175` lines / `167786` bytes
- `apps/api/saml.py`: `3487` lines / `147039` bytes
- `apps/accounts/views.py`: `3669` lines / `146477` bytes
- `apps/schools/marketing_page_definitions.py`: `3056` lines / `143830` bytes
- `apps/api/oneroster_results.py`: `3418` lines / `139254` bytes
- `apps/evals/views.py`: `3447` lines / `132498` bytes
- `apps/api/views_v1.py`: `2905` lines / `119916` bytes
- `apps/migration_cloud/views.py`: `2696` lines / `114910` bytes
- `apps/finance/models.py`: `3129` lines / `110777` bytes

## Documentation Drift

- Legacy documented app count: `54`
- Actual installed app count: `54`
- Drift detected: `False`

