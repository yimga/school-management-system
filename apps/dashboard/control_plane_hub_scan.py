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
        "siteconfig/theme_colors_control_plane.html",
        "studio_os/shell_control_plane.html",
        # Founder North Star: CP shell + bespoke metric strips (distinct from Phase 7 DE strips).
        "super/founder_dashboard.html",
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
