# Management command inventory (by purpose)

**Purpose:** Classify all management commands so we can delete obsolete ones, move operational ones behind admin/operator tooling, and keep a clean, documented command set. See also [Management commands index](../MANAGEMENT_COMMANDS_INDEX.md) for the central list and runbooks.

## Categories

| Purpose | Description | Policy |
|---------|-------------|--------|
| **Dev utility** | Local/dev only: seeds, test data, generators, diagrams | Keep; document as dev-only; do not run in production by default. |
| **Seed / bootstrap** | Platform or tenant bootstrap (regions, catalog, default tenant admin) | Keep; required for deploy/CI; document in runbooks. |
| **Migration / data repair** | One-off or rare: tenant migration, backfill, schema align | Keep; document when to run; prefer idempotent. |
| **Operational admin** | Recurring ops: retention, compliance, health, wind-down | Keep; consider exposing via admin UI or operator API. |
| **Debug / audit** | Checks, reports, verification, gap analysis | Keep for support; mark as debug-only where appropriate. |
| **Obsolete** | Superseded by another command or feature; unused | Delete or deprecate with clear message. |

## Sampled inventory (by app)

Commands are grouped by app; purpose is inferred from name and docstring. Full list: run `python manage.py help` or see `MANAGEMENT_COMMANDS_INDEX.md`.

### accounts

| Command | Purpose | Notes |
|---------|---------|------|
| ensure_superuser | Seed / bootstrap | Deploy/CI. |
| ensure_default_tenant_admin | Seed / bootstrap | Use for tenant admin bootstrap; supports --use-admin-user, --slug. |
| seed_render_users | Seed / bootstrap | Release; superuser + tenant admin. |
| create_teacher_parent_accounts | Dev utility | Demo accounts. |
| backfill_user_roles | Migration / data repair | One-off/rare. |
| check_roles | Debug / audit | Verification. |
| security_log_retention | Operational admin | Recurring. |
| list_expired_temporary_grants | Debug / audit | Support. |

### schools

| Command | Purpose | Notes |
|---------|---------|------|
| tenant_health_check | Operational admin | Health. |
| tenant_wind_down | Operational admin | Wind down tenant. |
| run_tenant_migrations | Migration / data repair | Per-tenant migrations. |
| migrate_tenant_schemas_one_by_one | Migration / data repair | Rare. |
| migrate_schools_to_tenants | Migration / data repair | One-off. |
| backfill_schooldomain | Migration / data repair | Backfill. |
| verify_tenant_rls | Debug / audit | Security/RLS. |
| verify_custom_domains | Debug / audit | Verification. |
| align_tenant_config | Migration / data repair | Align config. |
| validate_marketing_urls | Debug / audit | QA. |
| phase_i_gap_analysis | Debug / audit | Planning. |
| check_tenant_runtime | Debug / audit | Runtime check. |

### siteconfig

| Command | Purpose | Notes |
|---------|---------|------|
| bootstrap_runmycampus_platform | Seed / bootstrap | Platform bootstrap. |
| seed_global_regions, seed_regions, seed_country_profiles | Seed / bootstrap | Registry seed. |
| seed_workflow_dashboard_packs, seed_preview_fixtures | Seed / bootstrap | Catalog/content. |
| seed_provider_registry, seed_global_data | Seed / bootstrap | Registry/data. |
| bootstrap_platform_catalog | Seed / bootstrap | Catalog. |
| check_api_health, check_accessibility, check_integrations | Debug / audit | Health/checks. |
| export_ui_config, import_ui_config | Operational admin | Config sync. |
| compile_translations, i18n_commands | Operational admin | i18n. |
| recover_database | Operational admin | Recovery. |
| sync_regional_models | Migration / data repair | Sync. |
| run_workflows, test_core_workflows | Dev utility / Debug | Dev or smoke. |

### compliance

| Command | Purpose | Notes |
|---------|---------|------|
| check_compliance, compliance_auditor | Operational admin | Compliance. |
| archive_old_audits | Operational admin | Retention. |
| generate_compliance_reports, generate_legal_docs | Operational admin | Reports. |
| detect_threats, verify_data_integrity, verify_access_control | Debug / audit | Security/audit. |
| send_digest_alerts | Operational admin | Alerts. |
| seed_compliance_baseline | Seed / bootstrap | Baseline. |
| privacy_request | Operational admin | Privacy. |

### finance, marketplace, registries, automation, etc.

- **finance:** seed_finance_defaults (seed), apply_split_late_fees (ops), verify_bank_deposits (audit), report_finance_opt_in_gaps (audit), claim_suspense_payment (ops), integration_preflight (audit).
- **marketplace:** seed_marketplace_apps, seed_capability_registry (seed), marketplace_health_check (ops), marketplace_report_updates (audit).
- **registries:** seed_platform_registries, seed_terminology_registry (seed), verify_registry_coverage (audit).
- **automation:** seed_migration_profiles (seed).
- **observability:** db_health_check, synthetic_probe (ops/debug).
- **billing:** import_platform_billing_snapshot (migration/ops).
- **academics:** run_auto_promotion (ops), seed_demo, seed_buea_synthetic, seed_testdata_2425 (dev/seed), import_curriculum_nodes (migration), export_certification_pack (ops), fix_term_positions (repair), import_grades, grade_import_template (ops).
- **portal:** verify_onboarding_setup (audit), seed_kb_articles (seed), generate_kb_odt, import_docs_to_kb (content), cleanup_photo_upload_tokens (ops).
- **people:** check_badge_expiry_alerts (ops), revoke_audit_log_permissions (ops), attach_audit_triggers (migration).
- **reports:** export_report_cards_csv, generate_regional_reports (ops).
- **evals:** mark_completion (ops), import_grades (ops).
- **events:** process_event_outbox (ops), sync_legacy_webhooks_to_events (migration), retire_legacy_webhooks (migration).
- **customers:** ensure_tenant_schemas (bootstrap).
- **metadata:** seed_entity_catalog (seed).
- **policies:** seed_blueprint_policy_packs (seed).

## Next steps

1. Grep all `management/commands/*.py` and ensure each is in this inventory with a purpose.
2. Mark obsolete commands with a deprecation warning and removal date.
3. Move high-value operational commands behind admin or operator UI where appropriate.
4. Document dev-only commands so they are not run in production by default.
