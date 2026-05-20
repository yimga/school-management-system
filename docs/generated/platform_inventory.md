# Platform Inventory

- Installed app modules: `48`
- Python files: `4430`
- HTML templates: `1217`
- Markdown files: `1374`
- Migration files: `883`
- Management commands: `258` (full list in JSON key `management_commands_list`)
- `SiteSettings` refs (gross scan): `2159`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations): `68`
- `SiteSettings` refs (`apps/**/*.py`, excl. migrations+tests): `33`
- `get_solo()` refs: `211`
- `except Exception`: `1280`
- `cursor.execute()` (gross): `395`
- `cursor.execute()` (`apps`+`config` `.py`, excl. migrations): `40`
- `csrf_exempt` (substring, gross): `447`
- `csrf_exempt` decorator lines (`apps`+`config`, excl. migrations): `51`
- `AllowAny`: `138`
- `print()` (gross all `.py`): `2076`
- `print()` (`apps` product paths): `0`; `scripts/`: `1910`
- `gilead` matches (gross corpus): `16730` across `195` files
- `gilead` line hits (`apps`+`templates`+`config`, excl. migrations+tests+`management/commands`): `5`

Gross totals include migrations and broad file pools; use **scoped** lines around SQL/SiteSettings/Tenant gravity for trend tracking (see SOT §0 *Structural remediation stack*).
- Scoped-gravity **history** (last writes): `scripts/generated/scoped_gravity_trend.json` (updated with `generate_platform_inventory.py --write`; excluded from gross `gilead` JSON scan).

## Management Commands (full list)

Total: `258` commands. First 25 by app/command:

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
- `accounts` / `ensure_superadmin` — `apps/accounts/management/commands/ensure_superadmin.py`
- `accounts` / `ensure_superuser` — `apps/accounts/management/commands/ensure_superuser.py`
- `accounts` / `list_expired_temporary_grants` — `apps/accounts/management/commands/list_expired_temporary_grants.py`
- `accounts` / `refresh_saml_idp_metadata` — `apps/accounts/management/commands/refresh_saml_idp_metadata.py`
- `accounts` / `rotate_encryption_keys` — `apps/accounts/management/commands/rotate_encryption_keys.py`
- `accounts` / `security_log_retention` — `apps/accounts/management/commands/security_log_retention.py`
- `accounts` / `seed_render_users` — `apps/accounts/management/commands/seed_render_users.py`
- `analytics` / `ai_narrate_risk_digest` — `apps/analytics/management/commands/ai_narrate_risk_digest.py`
- `analytics` / `bootstrap_at_risk_registry` — `apps/analytics/management/commands/bootstrap_at_risk_registry.py`
- `analytics` / `build_student_embeddings` — `apps/analytics/management/commands/build_student_embeddings.py`
- `analytics` / `check_at_risk_calibration` — `apps/analytics/management/commands/check_at_risk_calibration.py`
- `analytics` / `check_at_risk_drift` — `apps/analytics/management/commands/check_at_risk_drift.py`
- `analytics` / `check_grade_prediction_calibration` — `apps/analytics/management/commands/check_grade_prediction_calibration.py`
- … and 233 more (see `platform_inventory.json` key `management_commands_list`).

## Public Endpoint Review

- Reviewed `csrf_exempt` files: `19`
- Reviewed `csrf_exempt` endpoints: `48`
- Reviewed `AllowAny` files: `3`
- Reviewed `AllowAny` occurrences: `7`

## SiteSettings Ownership

- `delete`: `1` fields
- `safe_platform_default`: `1` fields

## Successor Domain Imports Still Touching siteconfig

- `brand_experience`: `4` files
- `runtime_blueprints`: `1` files
- `plans_entitlements`: `1` files
- `global_registries`: `1` files
- `integrations_marketplace`: `18` files

## Largest Python Files

- `apps/schools/marketing_views.py`: `4091` lines / `163812` bytes
- `apps/schools/marketing_page_definitions.py`: `3056` lines / `143830` bytes
- `config/settings.py`: `2808` lines / `132074` bytes
- `apps/accounts/views.py`: `3334` lines / `130653` bytes
- `apps/evals/views.py`: `3270` lines / `125763` bytes
- `apps/api/views_v1.py`: `2890` lines / `119211` bytes
- `apps/migration_cloud/views.py`: `2608` lines / `111317` bytes
- `apps/siteconfig/views.py`: `2828` lines / `106976` bytes
- `apps/finance/models.py`: `3037` lines / `106339` bytes
- `apps/siteconfig/admin.py`: `2816` lines / `99012` bytes
- `apps/studio_os/views.py`: `2418` lines / `96234` bytes
- `apps/finance/tasks.py`: `2075` lines / `83551` bytes

## Documentation Drift

- Legacy documented app count: `48`
- Actual installed app count: `48`
- Drift detected: `False`

