"""
Control-plane template registry closure.

Every template that extends ``control_plane_base.html`` must either:
- appear in ``PHASE7_DASHBOARD_TEMPLATES`` (with Phase 7 marker + Phase 8 tag), or
- be listed in ``EXEMPT_CONTROL_PLANE_TEMPLATES`` (CRUD, shell, theme editor, etc.).

``scripts/verify_control_plane_hub_registry_drift.py`` and dashboard tests enforce this.
"""

from __future__ import annotations

import re
from pathlib import Path

from apps.dashboard.phase7_dashboard_templates import PHASE7_DASHBOARD_TEMPLATES

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "templates"

_EXTENDS_CP = re.compile(r'extends\s+["\']control_plane_base\.html["\']', re.MULTILINE)

# Intentionally not Phase-7 "full-page dashboard" registry targets.
EXEMPT_CONTROL_PLANE_TEMPLATES: frozenset[str] = frozenset(
    {
        "marketplace/blueprint_marketplace.html",
        "marketplace/compatibility_matrix.html",
        "marketplace/monetization_inspector.html",
        # Manager-safe tenant-scoped explainer; not a Phase 7 dashboard surface.
        "platform_runtime/configuration_module_detail.html",
        "platform_runtime/blueprint_apply.html",
        "platform_runtime/blueprint_detail.html",
        "platform_runtime/blueprint_impact.html",
        "platform_runtime/blueprint_installation_detail.html",
        "platform_runtime/blueprint_installations.html",
        "platform_runtime/blueprint_marketplace.html",
        "platform_runtime/blueprint_preview.html",
        "platform_runtime/blueprint_rollback.html",
        "platform_runtime/change_request_detail.html",
        "platform_runtime/change_requests.html",
        "platform_runtime/manager_offline_sync_center.html",
        "platform_runtime/pack_apply.html",
        "platform_runtime/pack_detail.html",
        "platform_runtime/pack_impact.html",
        "platform_runtime/pack_installation_detail.html",
        "platform_runtime/pack_installations.html",
        "platform_runtime/pack_marketplace.html",
        "platform_runtime/pack_preview.html",
        "platform_runtime/pack_rollback.html",
        "platform_runtime/pack_simulation.html",
        "platform_runtime/registry_health.html",
        "schools/super_advancement_hub.html",
        "schools/super_advancement_phase2_placeholder.html",
        "schools/super_ai_gateway_console.html",
        "schools/super_ai_model_hub.html",
        "schools/super_audit_export.html",
        "schools/super_billing_accounts_list.html",
        "schools/super_blueprints_catalog.html",
        "schools/super_compliance_overview.html",
        "schools/super_country_multipliers_list.html",
        "schools/super_create_school_wizard.html",
        "schools/super_crud_confirm_delete.html",
        "schools/super_crud_form.html",
        "schools/super_curriculum_packs.html",
        "schools/super_district_enterprise.html",
        "schools/super_education_systems.html",
        "schools/super_feature_toggles_list.html",
        "schools/super_fleet_governed_changes.html",
        "schools/super_geography.html",
        "schools/super_global_ai_version.html",
        "schools/super_global_ai_version_progress.html",
        "schools/super_governed_data_query.html",
        "schools/super_grading_list.html",
        "schools/super_group_campuses.html",
        "schools/super_incidents_list.html",
        "schools/super_learning_delivery_packs.html",
        "schools/super_legacy_sis_csv_preview.html",
        "schools/super_metadata_catalog_field_impact.html",
        "schools/super_migration_csv_diff.html",
        "schools/super_migration_profile_registry.html",
        "schools/super_migration_runs_list.html",
        "schools/super_ministry_report_stubs.html",
        "schools/super_one_sis_any_lms.html",
        "schools/super_operator_policy.html",
        "schools/super_plan_form.html",
        "schools/super_plans_list.html",
        "schools/super_platform_events.html",
        "schools/super_policies_catalog.html",
        "schools/super_regions_list.html",
        "schools/super_registries.html",
        "schools/super_runtime_inspector.html",
        "schools/super_security_surface_dashboard.html",
        "schools/super_schools_list.html",
        "schools/super_site_settings_edit.html",
        "schools/super_site_settings_list.html",
        "schools/super_sync_repair.html",
        "schools/super_support_auto_rules.html",
        "schools/super_support_on_call.html",
        "schools/super_tenant_health.html",
        "schools/super_workflow_packs.html",
        "schools/super_workflow_simulator.html",
        "sales/lead_create.html",
        "sales/lead_detail.html",
        "sales/pipeline_board.html",
        "siteconfig/config_mutation_audit_evidence.html",
        "siteconfig/entity_catalog_overview.html",
        "siteconfig/metadata_dynamic_fields_operator.html",
        "siteconfig/metadata_operator_hub.html",
        "siteconfig/region_comparison.html",
        "siteconfig/region_grading_scales_matrix.html",
        "siteconfig/region_validation_dashboard.html",
        "siteconfig/theme_colors.html",
        "studio_os/shell_control_plane.html",
        # Founder North Star: CP shell + bespoke metric strips (distinct from Phase 7 DE strips).
        "super/founder_dashboard.html",
        "super/ai_line_intent_coverage.html",
        "super/integrations/lms_audit_index.html",
        "super/integrations/lms_audit_exports.html",
        "super/integrations/idempotency_audit.html",
        "super/integrations/lms_index.html",
        "super/integrations/lms_provider.html",
        "super/sso/bindings_index.html",
        "super/wedges/_surface_base.html",
        "super/wedges/detail.html",
        "super/wedges/index.html",
        # Feedback / VoC hubs — operator-facing intake/roadmap surfaces, not Phase 7 DE strips.
        "feedback/product_roadmap.html",
        "feedback/voice_of_customer.html",
        # Manager operator control-plane page wrapper (CRUD-shaped; not a dashboard).
        "siteconfig/operator_control_plane_page.html",
        # Control-plane shell, AI center CRUD/workbench, migration/operator flows,
        # and setup/config pages that intentionally use the CP chrome but are not
        # Phase 7 full-page dashboard registry targets.
        "apicenter/super/ai_center_faq_candidates.html",
        "apicenter/super/ai_center_friction.html",
        "apicenter/super/ai_center_generate_kb.html",
        "apicenter/super/ai_center_home.html",
        "apicenter/super/ai_center_inventory.html",
        "apicenter/super/ai_center_kb_drafts.html",
        "apicenter/super/ai_center_query.html",
        "apicenter/super/ai_center_settings.html",
        "archetypes/cp_operator_dashboard.html",
        "backend_base_manager.html",
        "integrations_marketplace/manager_bulk_prestage.html",
        "integrations_marketplace/manager_rollup.html",
        "lifecycle/bulk_create.html",
        "lifecycle/clone.html",
        "lifecycle/jobs_dashboard.html",
        "lifecycle/rapid_create.html",
        "lifecycle/timeline.html",
        "migration_cloud/anomaly_nudge.html",
        "migration_cloud/assets.html",
        "migration_cloud/attach_source.html",
        "migration_cloud/bind_school.html",
        "migration_cloud/bundle_detail.html",
        "migration_cloud/canonical_template_picker.html",
        "migration_cloud/conflicts.html",
        "migration_cloud/connector/operator.html",
        "migration_cloud/console.html",
        "migration_cloud/handoff_doc.html",
        "migration_cloud/intake_new.html",
        "migration_cloud/operator/audit_dashboard.html",
        "migration_cloud/operator/command_center.html",
        "migration_cloud/operator/dlq_list.html",
        "migration_cloud/operator/dsar_runbook.html",
        "migration_cloud/operator/maa_counsel_activate.html",
        "migration_cloud/operator/smoke_history.html",
        "migration_cloud/operator/smoke_trigger.html",
        "migration_cloud/operator/token_list.html",
        "migration_cloud/operator/token_mint.html",
        "migration_cloud/operator/token_mint_result.html",
        "migration_cloud/operator/token_rotation_chain.html",
        "migration_cloud/operator/webhook_audit.html",
        "migration_cloud/operator/webhook_delivery_log.html",
        "migration_cloud/operator/webhook_list.html",
        "migration_cloud/operator/webhook_subscribe.html",
        "migration_cloud/progress.html",
        "migration_cloud/super/health.html",
        "migration_cloud/super/lms_diagnostics.html",
        "migration_cloud/super/lms_diagnostics_retention_preview.html",
        "migration_cloud/super/maa_v2_promotion.html",
        "migration_cloud/super/vendor_write_status.html",
        "schoolops/operator/meal_plan_analytics.html",
        "schoolops/super/email_configure.html",
        "schoolops/super/email_health.html",
        "schoolops/super/signup_diagnostics.html",
        "schools/manager_feature_gap_register.html",
        "schools/manager_feedback_loop.html",
        "schools/manager_lane2_readiness.html",
        "schools/manager_public_to_product_matrix.html",
        "schools/mat_group_hub/dashboard.html",
        "schools/mat_group_hub/detail.html",
        "schools/mat_group_hub/edit.html",
        "schools/super_offboarding_queue.html",
        "schools/super_operator_team_detail.html",
        "schools/super_operator_team_invite.html",
        "schools/super_operator_team_promote.html",
        "schools/super_operator_team_roster.html",
        "setup_studio/operator_wizard.html",
        "setup_studio/operator_wizard_index.html",
        "setup_studio/super_activation_dashboard.html",
        "siteconfig/config_mutation_audit_evidence.html",
        "siteconfig/super/cockpit_configure.html",
        "siteconfig/super/cockpit_health.html",
        "siteconfig/super/cockpit_previews.html",
        "siteconfig/super_dashboard_defaults_admin.html",
        "siteconfig/super/marketing_voice_configure.html",
        "siteconfig/super/theme_personality_configure.html",
        "siteconfig/theme_builder_control_plane.html",
        "siteconfig/theme_experience_hub_control_plane.html",
        "siteconfig/zero_ticket_shell.html",
    }
)


def iter_control_plane_template_relpaths(templates_dir: Path = TEMPLATES_DIR) -> list[str]:
    """Return relative paths (posix) under templates/ that extend control_plane_base."""
    found: list[str] = []
    for path in sorted(templates_dir.rglob("*.html")):
        rel = path.relative_to(templates_dir).as_posix()
        if "partials/" in rel or "/components/" in rel or rel.startswith("components/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _EXTENDS_CP.search(text):
            found.append(rel)
    return found


def unlisted_control_plane_templates(templates_dir: Path = TEMPLATES_DIR) -> list[str]:
    """Paths extending control_plane_base that are neither registered nor exempt."""
    registered = frozenset(PHASE7_DASHBOARD_TEMPLATES)
    exempt = EXEMPT_CONTROL_PLANE_TEMPLATES
    orphans: list[str] = []
    for rel in iter_control_plane_template_relpaths(templates_dir):
        if rel in registered or rel in exempt:
            continue
        orphans.append(rel)
    return sorted(orphans)


def assert_control_plane_hub_registry_closed(templates_dir: Path = TEMPLATES_DIR) -> None:
    bad = unlisted_control_plane_templates(templates_dir)
    if bad:
        raise AssertionError(
            "control_plane_base templates not in PHASE7_DASHBOARD_TEMPLATES and not EXEMPT: "
            + ", ".join(bad)
        )

    overlap = EXEMPT_CONTROL_PLANE_TEMPLATES & frozenset(PHASE7_DASHBOARD_TEMPLATES)
    if overlap:
        raise AssertionError(
            "EXEMPT_CONTROL_PLANE_TEMPLATES overlaps PHASE7_DASHBOARD_TEMPLATES: "
            + ", ".join(sorted(overlap))
        )
