# Platform Inventory

- Installed app modules: `41`
- Python files: `2079`
- HTML templates: `564`
- Markdown files: `993`
- Migration files: `636`
- Management commands: `144` (full list in JSON key `management_commands_list`)
- `SiteSettings` refs: `1158`
- `get_solo()` refs: `182`
- `except Exception`: `219`
- `cursor.execute()`: `352`
- `csrf_exempt`: `141`
- `AllowAny`: `63`
- `print()`: `544`
- `gilead` matches: `713` across `138` files


## Management Commands (full list)

Total: `144` commands. First 25 by app/command:

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
- … and 119 more (see `platform_inventory.json` key `management_commands_list`).

## Public Endpoint Review

- Reviewed `csrf_exempt` files: `12`
- Reviewed `csrf_exempt` endpoints: `34`
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

- `apps/schools/marketing_page_definitions.py`: `2861` lines / `135837` bytes
- `apps/schools/marketing_views.py`: `3034` lines / `120110` bytes
- `apps/siteconfig/admin.py`: `3277` lines / `116827` bytes
- `apps/accounts/views.py`: `3009` lines / `114677` bytes
- `apps/evals/views.py`: `3100` lines / `114435` bytes
- `apps/api/views_v1.py`: `2468` lines / `103258` bytes
- `apps/portal/views_parent.py`: `2504` lines / `98728` bytes
- `apps/finance/models.py`: `2807` lines / `98407` bytes
- `apps/siteconfig/models.py`: `2482` lines / `96669` bytes
- `apps/siteconfig/views.py`: `2377` lines / `88300` bytes
- `apps/finance/tasks.py`: `2069` lines / `84718` bytes
- `apps/siteconfig/management/commands/seed_admin_dashboard_palettes.py`: `1495` lines / `63960` bytes

## Documentation Drift

- Legacy documented app count: `38`
- Actual installed app count: `41`
- Drift detected: `True`

