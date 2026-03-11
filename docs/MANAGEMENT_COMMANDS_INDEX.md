# Management Commands Index (Path-to-10 — Governance)

**Purpose:** Classify all management commands for rationalization. Operational commands should have clear ownership; obsolete commands should be deleted; critical ops may be exposed via control-plane UI.

## Categories

- **seed** — Bootstrap, fixtures, one-time or rare data setup
- **ops** — Recurring operational tasks (health checks, syncs, reports, reminders)
- **migration** — Schema/data migration or tenant migration
- **dev** — Development and debugging (diagrams, parity checks, test workflows)
- **compliance** — Compliance, audit, legal, privacy
- **other** — Unclassified

## By app (command name)

| App | Command | Category | Notes |
|-----|---------|----------|-------|
| academics | export_certification_pack, fix_term_positions, import_curriculum_nodes, run_auto_promotion, seed_buea_synthetic, seed_demo, seed_testdata_2425 | seed / ops | |
| accounts | backfill_user_roles, check_roles, create_teacher_parent_accounts, ensure_default_tenant_admin, ensure_gilead_admin, ensure_superadmin, ensure_superuser, list_expired_temporary_grants, security_log_retention, seed_render_users | seed / ops | |
| analytics | compute_benchmark_aggregates, compute_nightly_risk, send_deadline_reminders | ops | |
| automation | seed_migration_profiles | seed | |
| billing | import_platform_billing_snapshot, run_platform_billing_lifecycle, run_revenue_share_payouts | ops | |
| communication | sync_department_threads | ops | |
| compliance | archive_old_audits, check_compliance, cleanup_expired_rules, compliance_auditor, detect_threats, export_compliance_evidence_pack, generate_compliance_reports, generate_legal_docs, privacy_request, purge_compliance_data, seed_compliance_baseline, send_digest_alerts, verify_access_control, verify_data_integrity | compliance / ops | |
| customers | ensure_tenant_schemas | migration | |
| evals | grade_import_template, import_grades, mark_completion | ops | |
| events | process_event_outbox, process_webhook_deliveries, retire_legacy_webhooks, sync_legacy_webhooks_to_events | ops | |
| finance | apply_split_late_fees, claim_suspense_payment, import_bank_statement, integration_preflight, report_finance_opt_in_gaps, seed_finance_defaults, send_payment_reminders, verify_bank_deposits | ops / seed | |
| marketplace | marketplace_health_check, marketplace_report_updates, seed_capability_registry, seed_marketplace_apps | ops / seed | |
| metadata | seed_business_glossary, seed_entity_catalog | seed | |
| observability | db_health_check, synthetic_probe | ops | |
| payroll | run_payroll_cycle | ops | |
| people | attach_audit_triggers, check_badge_expiry_alerts, revoke_audit_log_permissions | ops / dev | |
| policies | seed_blueprint_policy_packs, update_blueprint_bundles | seed / ops | |
| portal | cleanup_photo_upload_tokens, generate_kb_odt, import_docs_to_kb, seed_faqs, seed_kb_articles, verify_kb_exports, verify_onboarding_setup | ops / seed | |
| registries | seed_platform_registries, seed_terminology_registry, verify_registry_coverage | seed / ops | |
| reports | export_report_cards_csv, generate_regional_reports, send_scheduled_reports | ops | |
| schools | align_tenant_config, backfill_schooldomain, check_tenant_runtime, migrate_schools_to_tenants, migrate_tenant_schemas_one_by_one, phase_i_gap_analysis, run_tenant_migrations, tenant_health_check, tenant_wind_down, validate_marketing_urls, verify_custom_domains, verify_tenant_rls | migration / ops | |
| siteconfig | audit_tenant_models, backfill_service_integrations, bootstrap_platform_catalog, bootstrap_runmycampus_platform, calculate_monthly_revenue_stats, check_accessibility, check_api_health, check_branding_law, check_integrations, check_ui_parity, clone_region, compile_translations, dispatch_webhook_deliveries, export_config, export_ui_config, generate_models_diagram, i18n_commands, import_config, import_ui_config, migrate_dashboard_layouts, normalize_ui_config, recover_database, run_phase7_checks, run_workflows, seed_admin_dashboard_palettes, seed_country_profiles, seed_global_brand_registry, seed_global_data, seed_global_regions, seed_preview_fixtures, seed_provider_registry, seed_regions, seed_workflow_dashboard_packs, sync_regional_models, test_core_workflows, validate_regions, verify_region_coverage | seed / ops / dev / migration | |

## Next steps (Phase 10)

- Delete obsolete commands (e.g. ensure_gilead_admin if fully superseded by ensure_superuser/ensure_default_tenant_admin).
- Expose critical ops (tenant_health_check, marketplace_health_check, db_health_check, etc.) via control-plane UI or scheduled jobs with visibility.
- Document owner per command family.

**Reference:** `docs/REMAINING_WORK.md` task 9.1; `docs/PHASE_10_BACKLOG.md`.
