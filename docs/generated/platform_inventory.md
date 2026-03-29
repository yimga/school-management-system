# Platform Inventory

- Installed app modules: `42`
- Python files: `2421`
- HTML templates: `649`
- Markdown files: `1032`
- Migration files: `703`
- Management commands: `157` (full list in JSON key `management_commands_list`)
- `SiteSettings` refs (gross scan): `1372`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations): `59`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations+tests): `1`
- `get_solo()` refs: `196`
- `except Exception`: `263`
- `cursor.execute()` (gross): `366`
- `cursor.execute()` (`apps`+`config` `.py`, excl. migrations): `26`
- `csrf_exempt` (substring, gross): `174`
- `csrf_exempt` decorator lines (`apps`+`config`, excl. migrations): `37`
- `AllowAny`: `81`
- `print()` (gross all `.py`): `815`
- `print()` (`apps` product paths): `0`; `scripts/`: `720`
- `gilead` matches (gross corpus): `974` across `150` files
- `gilead` line hits (`apps`+`templates`+`config`, excl. migrations+tests+`management/commands`): `0`

Gross totals include migrations and broad file pools; use **scoped** lines around SQL/SiteSettings/Tenant gravity for trend tracking (see SOT §0 *Structural remediation stack*).
- Scoped-gravity **history** (last writes): `scripts/generated/scoped_gravity_trend.json` (updated with `generate_platform_inventory.py --write`; excluded from gross `gilead` JSON scan).

## Management Commands (full list)

Total: `157` commands. First 25 by app/command:

- `academics` / `export_certification_pack` — `apps/academics/management/commands/export_certification_pack.py`
- `academics` / `fix_term_positions` — `apps/academics/management/commands/fix_term_positions.py`
- `academics` / `import_curriculum_nodes` — `apps/academics/management/commands/import_curriculum_nodes.py`
- `academics` / `run_auto_promotion` — `apps/academics/management/commands/run_auto_promotion.py`
- `academics` / `seed_buea_synthetic` — `apps/academics/management/commands/seed_buea_synthetic.py`
- `academics` / `seed_demo` — `apps/academics/management/commands/seed_demo.py`
- `academics` / `seed_testdata_2425` — `apps/academics/management/commands/seed_testdata_2425.py`
- `accounts` / `backfill_user_roles` — `apps/accounts/management/commands/backfill_user_roles.py`
- `accounts` / `check_roles` — `apps/accounts/management/commands/check_roles.py`
- `accounts` / `create_teacher_parent_accounts` — `apps/accounts/management/commands/create_teacher_parent_accounts.py`
- `accounts` / `ensure_default_tenant_admin` — `apps/accounts/management/commands/ensure_default_tenant_admin.py`
- `accounts` / `ensure_superadmin` — `apps/accounts/management/commands/ensure_superadmin.py`
- `accounts` / `ensure_superuser` — `apps/accounts/management/commands/ensure_superuser.py`
- `accounts` / `list_expired_temporary_grants` — `apps/accounts/management/commands/list_expired_temporary_grants.py`
- `accounts` / `refresh_saml_idp_metadata` — `apps/accounts/management/commands/refresh_saml_idp_metadata.py`
- `accounts` / `security_log_retention` — `apps/accounts/management/commands/security_log_retention.py`
- `accounts` / `seed_render_users` — `apps/accounts/management/commands/seed_render_users.py`
- `analytics` / `compute_benchmark_aggregates` — `apps/analytics/management/commands/compute_benchmark_aggregates.py`
- `analytics` / `compute_nightly_risk` — `apps/analytics/management/commands/compute_nightly_risk.py`
- `analytics` / `send_deadline_reminders` — `apps/analytics/management/commands/send_deadline_reminders.py`
- `automation` / `migration_legacy_data_audit` — `apps/automation/management/commands/migration_legacy_data_audit.py`
- `automation` / `seed_migration_profiles` — `apps/automation/management/commands/seed_migration_profiles.py`
- `billing` / `import_platform_billing_snapshot` — `apps/billing/management/commands/import_platform_billing_snapshot.py`
- `billing` / `run_platform_billing_lifecycle` — `apps/billing/management/commands/run_platform_billing_lifecycle.py`
- `billing` / `run_revenue_share_payouts` — `apps/billing/management/commands/run_revenue_share_payouts.py`
- … and 132 more (see `platform_inventory.json` key `management_commands_list`).

## Public Endpoint Review

- Reviewed `csrf_exempt` files: `13`
- Reviewed `csrf_exempt` endpoints: `37`
- Reviewed `AllowAny` files: `1`
- Reviewed `AllowAny` occurrences: `2`

## SiteSettings Ownership

- `delete`: `1` fields
- `safe_platform_default`: `1` fields

## Successor Domain Imports Still Touching siteconfig

- `brand_experience`: `2` files
- `runtime_blueprints`: `1` files
- `plans_entitlements`: `1` files
- `global_registries`: `1` files
- `integrations_marketplace`: `1` files

## Largest Python Files

- `apps/schools/marketing_page_definitions.py`: `2861` lines / `135837` bytes
- `apps/schools/marketing_views.py`: `3188` lines / `126054` bytes
- `apps/api/views_v1.py`: `2847` lines / `118196` bytes
- `apps/evals/views.py`: `3100` lines / `114885` bytes
- `apps/accounts/views.py`: `3009` lines / `114677` bytes
- `apps/finance/models.py`: `2814` lines / `98677` bytes
- `apps/siteconfig/admin.py`: `2814` lines / `98649` bytes
- `apps/siteconfig/views.py`: `2495` lines / `93328` bytes
- `apps/studio_os/views.py`: `2164` lines / `85549` bytes
- `apps/finance/tasks.py`: `2062` lines / `82393` bytes
- `apps/portal/views_ai_gateway.py`: `1936` lines / `71556` bytes
- `config/settings.py`: `1556` lines / `70388` bytes

## Documentation Drift

- Legacy documented app count: `42`
- Actual installed app count: `42`
- Drift detected: `False`

