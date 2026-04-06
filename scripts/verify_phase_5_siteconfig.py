#!/usr/bin/env python3
"""
ZIP Phase 5 — SiteSettings / siteconfig dismantling (repository gate).

Verifies:
- Canonical docs exist and reference the ownership / inventory discipline
- domain_ownership module defines field classification (inventory + code stay aligned)
- ``verify_domain_ownership_exact_storage.py``: every ``EXACT_FIELD_OWNERS`` key is a
  RuntimeDefaults first-class column, registered virtual-only, or row-metadata delete bucket;
  every first-class column has an explicit ``EXACT_FIELD_OWNERS`` row
- lint_tenant_settings: no get_solo() in tenant-facing app trees

Includes get_solo lint and SiteSettings.objects.* lint in tenant app trees.
Phase B Batch 0: asserts ``0162_phase_b_slim_sitesettings.py`` exists.
Phase B Batch 1: asserts ``brand_experience/0002_platform_global_branding.py`` exists.
Phase B Batch 3: asserts ``siteconfig/0163_phase_b_batch3_drop_sitesettings_branding_columns.py`` exists.
Batches 4-13: asserts ``platform_runtime/0007_platform_phase_b_domain_snapshots.py`` exists.
RuntimeDefaults first-class columns: asserts ``0009`` through ``0034`` migration artifacts exist
(including Phase B snapshot metadata extensions and marketplace secret column splits).
Also asserts ``0035_platform_integration_webhook_event`` (Phase B–style inbound webhook audit),
``0036_platform_report_platform_sku_default`` (operator default report-platform bundle singleton),
``0037_runtimedefaults_marketplace_partner_client_secret_first_class``,
``0038_platform_operator_playbook_link`` (typed operator deep-link table),
``0039_platform_operator_truth_hub_link`` (Runtime truth hub curated links), and
``0040_platform_operator_phase_b_link`` (Phase B snapshot diff curated links), and
``0041_platform_operator_workflow_simulator_link`` (workflow simulator curated links), and
``0042_platform_operator_support_dashboard_link`` (support dashboard curated links), and
``0043_platform_operator_tenant_health_link`` (tenant health monitor curated links), and
``0044_platform_operator_command_center_link`` (mission / command center curated links), and
``0045_platform_operator_orchestration_workbench_link`` (orchestration workbench curated links).
Table/singleton after migrate: ``scripts/verify_phase_b_execution.py``.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
Exit 0 = gate MET; non-zero = fix before release.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

REQUIRED_DOCS: tuple[tuple[Path, str], ...] = (
    (ROOT / "docs" / "site_settings_usage_inventory.md", "SiteSettings usage inventory"),
    (ROOT / "docs" / "domain_ownership.md", "Domain ownership"),
    (ROOT / "docs" / "SITECONFIG_OWNERSHIP_MIGRATION.md", "Ownership migration plan"),
    (ROOT / "docs" / "SITECONFIG_FREEZE_POLICY.md", "Siteconfig freeze policy"),
    (ROOT / "docs" / "SITESETTINGS_RUNTIME_DECOMPOSITION.md", "Runtime decomposition"),
)

DOMAIN_OWNERSHIP_PY = ROOT / "apps" / "siteconfig" / "domain_ownership.py"
LINT_SCRIPT = ROOT / "scripts" / "lint_tenant_settings.py"
# Phase B Batch 0 — slim SiteSettings + payload bridge (SITECONFIG_OWNERSHIP_MIGRATION.md).
PHASE_B_BATCH0_MIGRATION = (
    ROOT / "apps" / "siteconfig" / "migrations" / "0162_phase_b_slim_sitesettings.py"
)
PHASE_B_BATCH1_MIGRATION = (
    ROOT / "apps" / "brand_experience" / "migrations" / "0002_platform_global_branding.py"
)
PHASE_B_BATCH3_MIGRATION = (
    ROOT
    / "apps"
    / "siteconfig"
    / "migrations"
    / "0163_phase_b_batch3_drop_sitesettings_branding_columns.py"
)
# Phase B Batches 4-13: one JSON row per non-brand ownership domain.
PHASE_B_DOMAIN_SNAPSHOT_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0007_platform_phase_b_domain_snapshots.py"
)
RUNTIMEDEFAULTS_FIRST_CLASS_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0009_runtimedefaults_preview_integration_columns.py"
)
RUNTIMEDEFAULTS_PUBLIC_BRAND_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0010_runtimedefaults_public_brand_colors.py"
)
RUNTIMEDEFAULTS_META_DOMAIN_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0011_runtimedefaults_meta_description_branded_domain.py"
)
RUNTIMEDEFAULTS_TAGLINE_SCHOOL_CODE_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0012_runtimedefaults_tagline_school_code.py"
)
RUNTIMEDEFAULTS_COMPANY_IDENTITY_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0013_runtimedefaults_company_identity_strings.py"
)
RUNTIMEDEFAULTS_IDENTITY_GEO_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0014_runtimedefaults_identity_and_geo_strings.py"
)
RUNTIMEDEFAULTS_REGISTRY_STRINGS_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0015_runtimedefaults_registry_strings_batch.py"
)
RUNTIMEDEFAULTS_ADMISSION_ADMIN_PORTAL_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0016_runtimedefaults_admission_and_admin_portal_defaults.py"
)
RUNTIMEDEFAULTS_BRAND_RUNTIME_DASHBOARD_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0017_runtimedefaults_brand_runtime_dashboard_batch.py"
)
RUNTIMEDEFAULTS_PORTAL_FEED_BATCH_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0018_runtimedefaults_portal_feed_batch.py"
)
RUNTIMEDEFAULTS_BRAND_PALETTE_SOCIAL_BATCH_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0019_runtimedefaults_brand_palette_and_social_batch.py"
)
RUNTIMEDEFAULTS_PORTAL_THEME_POLICY_BATCH_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0020_runtimedefaults_portal_theme_policy_batch.py"
)
RUNTIMEDEFAULTS_THEME_SURFACE_BATCH_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0021_runtimedefaults_theme_surface_batch.py"
)
RUNTIMEDEFAULTS_POLICY_RUNTIME_TOGGLES_BATCH_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0022_runtimedefaults_policy_runtime_toggles_batch.py"
)
RUNTIMEDEFAULTS_REPORTS_THEMEPACK_BATCH_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0023_runtimedefaults_reports_themepack_batch.py"
)
RUNTIMEDEFAULTS_POLICY_REPORTS_INTERVAL_BATCH_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0024_runtimedefaults_policy_reports_interval_batch.py"
)
RUNTIMEDEFAULTS_POLICY_MAPS_COMPLIANCE_BATCH_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0025_runtimedefaults_policy_maps_and_compliance_batch.py"
)
PHASE_B_SNAPSHOT_TYPED_METADATA_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0026_platformphasebdomainsnapshot_typed_metadata.py"
)
PHASE_B_SNAPSHOT_KEY_CHECKSUMS_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0027_platformphasebdomainsnapshot_key_checksums.py"
)
RUNTIMEDEFAULTS_REPORT_DOWNLOADS_ENABLED_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0028_runtimedefaults_report_downloads_enabled.py"
)
RUNTIMEDEFAULTS_SMS_API_KEY_FIRST_CLASS_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0029_runtimedefaults_sms_api_key_first_class.py"
)
RUNTIMEDEFAULTS_AI_PROVIDER_API_KEY_FIRST_CLASS_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0030_runtimedefaults_ai_provider_api_key_first_class.py"
)
RUNTIMEDEFAULTS_WHATSAPP_API_TOKEN_FIRST_CLASS_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0031_runtimedefaults_whatsapp_api_token_first_class.py"
)
RUNTIMEDEFAULTS_MARKSHEET_OCR_API_KEY_FIRST_CLASS_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0032_runtimedefaults_marksheet_ocr_api_key_first_class.py"
)
RUNTIMEDEFAULTS_SMTP_PASSWORD_FIRST_CLASS_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0033_runtimedefaults_smtp_password_first_class.py"
)
RUNTIMEDEFAULTS_WEBHOOK_SIGNING_SECRET_FIRST_CLASS_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0034_runtimedefaults_webhook_signing_secret_first_class.py"
)
PLATFORM_INTEGRATION_WEBHOOK_EVENT_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0035_platform_integration_webhook_event.py"
)
PLATFORM_REPORT_PLATFORM_SKU_DEFAULT_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0036_platform_report_platform_sku_default.py"
)
RUNTIMEDEFAULTS_MARKETPLACE_PARTNER_CLIENT_SECRET_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0037_runtimedefaults_marketplace_partner_client_secret_first_class.py"
)
PLATFORM_OPERATOR_PLAYBOOK_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0038_platform_operator_playbook_link.py"
)
PLATFORM_OPERATOR_TRUTH_HUB_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0039_platform_operator_truth_hub_link.py"
)
PLATFORM_OPERATOR_PHASE_B_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0040_platform_operator_phase_b_link.py"
)
PLATFORM_OPERATOR_WORKFLOW_SIMULATOR_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0041_platform_operator_workflow_simulator_link.py"
)
PLATFORM_OPERATOR_SUPPORT_DASHBOARD_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0042_platform_operator_support_dashboard_link.py"
)
PLATFORM_OPERATOR_TENANT_HEALTH_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0043_platform_operator_tenant_health_link.py"
)
PLATFORM_OPERATOR_COMMAND_CENTER_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0044_platform_operator_command_center_link.py"
)
PLATFORM_OPERATOR_ORCHESTRATION_WORKBENCH_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0045_platform_operator_orchestration_workbench_link.py"
)
PLATFORM_OPERATOR_SUPER_DASHBOARD_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0046_platform_operator_super_dashboard_link.py"
)
PLATFORM_OPERATOR_SUPER_SCHOOLS_LIST_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0047_platform_operator_super_schools_list_link.py"
)
PLATFORM_OPERATOR_SUPER_ANALYTICS_OVERVIEW_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0048_platform_operator_super_analytics_overview_link.py"
)
PLATFORM_OPERATOR_PLATFORM_HUB_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0049_platform_operator_platform_hub_link.py"
)
PLATFORM_OPERATOR_MIGRATION_CLOUD_LINK_MIGRATION = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0050_platform_operator_migration_cloud_link.py"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify ZIP Phase 5 SiteSettings / siteconfig dismantling."
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"--base directory not found: {raw_base}")
    return base


def _configure_root(base: Path) -> None:
    global ROOT
    global REQUIRED_DOCS
    global DOMAIN_OWNERSHIP_PY
    global LINT_SCRIPT
    global PHASE_B_BATCH0_MIGRATION
    global PHASE_B_BATCH1_MIGRATION
    global PHASE_B_BATCH3_MIGRATION
    global PHASE_B_DOMAIN_SNAPSHOT_MIGRATION
    global RUNTIMEDEFAULTS_FIRST_CLASS_MIGRATION
    global RUNTIMEDEFAULTS_PUBLIC_BRAND_MIGRATION
    global RUNTIMEDEFAULTS_META_DOMAIN_MIGRATION
    global RUNTIMEDEFAULTS_TAGLINE_SCHOOL_CODE_MIGRATION
    global RUNTIMEDEFAULTS_COMPANY_IDENTITY_MIGRATION
    global RUNTIMEDEFAULTS_IDENTITY_GEO_MIGRATION
    global RUNTIMEDEFAULTS_REGISTRY_STRINGS_MIGRATION
    global RUNTIMEDEFAULTS_ADMISSION_ADMIN_PORTAL_MIGRATION
    global RUNTIMEDEFAULTS_BRAND_RUNTIME_DASHBOARD_MIGRATION
    global RUNTIMEDEFAULTS_PORTAL_FEED_BATCH_MIGRATION
    global RUNTIMEDEFAULTS_BRAND_PALETTE_SOCIAL_BATCH_MIGRATION
    global RUNTIMEDEFAULTS_PORTAL_THEME_POLICY_BATCH_MIGRATION
    global RUNTIMEDEFAULTS_THEME_SURFACE_BATCH_MIGRATION
    global RUNTIMEDEFAULTS_POLICY_RUNTIME_TOGGLES_BATCH_MIGRATION
    global RUNTIMEDEFAULTS_REPORTS_THEMEPACK_BATCH_MIGRATION
    global RUNTIMEDEFAULTS_POLICY_REPORTS_INTERVAL_BATCH_MIGRATION
    global RUNTIMEDEFAULTS_POLICY_MAPS_COMPLIANCE_BATCH_MIGRATION
    global PHASE_B_SNAPSHOT_TYPED_METADATA_MIGRATION
    global PHASE_B_SNAPSHOT_KEY_CHECKSUMS_MIGRATION
    global RUNTIMEDEFAULTS_REPORT_DOWNLOADS_ENABLED_MIGRATION
    global RUNTIMEDEFAULTS_SMS_API_KEY_FIRST_CLASS_MIGRATION
    global RUNTIMEDEFAULTS_AI_PROVIDER_API_KEY_FIRST_CLASS_MIGRATION
    global RUNTIMEDEFAULTS_WHATSAPP_API_TOKEN_FIRST_CLASS_MIGRATION
    global RUNTIMEDEFAULTS_MARKSHEET_OCR_API_KEY_FIRST_CLASS_MIGRATION
    global RUNTIMEDEFAULTS_SMTP_PASSWORD_FIRST_CLASS_MIGRATION
    global RUNTIMEDEFAULTS_WEBHOOK_SIGNING_SECRET_FIRST_CLASS_MIGRATION
    global PLATFORM_INTEGRATION_WEBHOOK_EVENT_MIGRATION
    global PLATFORM_REPORT_PLATFORM_SKU_DEFAULT_MIGRATION
    global RUNTIMEDEFAULTS_MARKETPLACE_PARTNER_CLIENT_SECRET_MIGRATION
    global PLATFORM_OPERATOR_PLAYBOOK_LINK_MIGRATION
    global PLATFORM_OPERATOR_TRUTH_HUB_LINK_MIGRATION
    global PLATFORM_OPERATOR_PHASE_B_LINK_MIGRATION
    global PLATFORM_OPERATOR_WORKFLOW_SIMULATOR_LINK_MIGRATION
    global PLATFORM_OPERATOR_SUPPORT_DASHBOARD_LINK_MIGRATION
    global PLATFORM_OPERATOR_TENANT_HEALTH_LINK_MIGRATION
    global PLATFORM_OPERATOR_COMMAND_CENTER_LINK_MIGRATION
    global PLATFORM_OPERATOR_ORCHESTRATION_WORKBENCH_LINK_MIGRATION
    global PLATFORM_OPERATOR_SUPER_DASHBOARD_LINK_MIGRATION
    global PLATFORM_OPERATOR_SUPER_SCHOOLS_LIST_LINK_MIGRATION
    global PLATFORM_OPERATOR_SUPER_ANALYTICS_OVERVIEW_LINK_MIGRATION
    global PLATFORM_OPERATOR_PLATFORM_HUB_LINK_MIGRATION
    global PLATFORM_OPERATOR_MIGRATION_CLOUD_LINK_MIGRATION

    ROOT = base
    REQUIRED_DOCS = (
        (ROOT / "docs" / "site_settings_usage_inventory.md", "SiteSettings usage inventory"),
        (ROOT / "docs" / "domain_ownership.md", "Domain ownership"),
        (ROOT / "docs" / "SITECONFIG_OWNERSHIP_MIGRATION.md", "Ownership migration plan"),
        (ROOT / "docs" / "SITECONFIG_FREEZE_POLICY.md", "Siteconfig freeze policy"),
        (ROOT / "docs" / "SITESETTINGS_RUNTIME_DECOMPOSITION.md", "Runtime decomposition"),
    )
    DOMAIN_OWNERSHIP_PY = ROOT / "apps" / "siteconfig" / "domain_ownership.py"
    LINT_SCRIPT = ROOT / "scripts" / "lint_tenant_settings.py"
    PHASE_B_BATCH0_MIGRATION = ROOT / "apps" / "siteconfig" / "migrations" / "0162_phase_b_slim_sitesettings.py"
    PHASE_B_BATCH1_MIGRATION = ROOT / "apps" / "brand_experience" / "migrations" / "0002_platform_global_branding.py"
    PHASE_B_BATCH3_MIGRATION = ROOT / "apps" / "siteconfig" / "migrations" / "0163_phase_b_batch3_drop_sitesettings_branding_columns.py"
    PHASE_B_DOMAIN_SNAPSHOT_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0007_platform_phase_b_domain_snapshots.py"
    RUNTIMEDEFAULTS_FIRST_CLASS_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0009_runtimedefaults_preview_integration_columns.py"
    RUNTIMEDEFAULTS_PUBLIC_BRAND_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0010_runtimedefaults_public_brand_colors.py"
    RUNTIMEDEFAULTS_META_DOMAIN_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0011_runtimedefaults_meta_description_branded_domain.py"
    RUNTIMEDEFAULTS_TAGLINE_SCHOOL_CODE_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0012_runtimedefaults_tagline_school_code.py"
    RUNTIMEDEFAULTS_COMPANY_IDENTITY_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0013_runtimedefaults_company_identity_strings.py"
    RUNTIMEDEFAULTS_IDENTITY_GEO_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0014_runtimedefaults_identity_and_geo_strings.py"
    RUNTIMEDEFAULTS_REGISTRY_STRINGS_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0015_runtimedefaults_registry_strings_batch.py"
    RUNTIMEDEFAULTS_ADMISSION_ADMIN_PORTAL_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0016_runtimedefaults_admission_and_admin_portal_defaults.py"
    RUNTIMEDEFAULTS_BRAND_RUNTIME_DASHBOARD_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0017_runtimedefaults_brand_runtime_dashboard_batch.py"
    RUNTIMEDEFAULTS_PORTAL_FEED_BATCH_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0018_runtimedefaults_portal_feed_batch.py"
    RUNTIMEDEFAULTS_BRAND_PALETTE_SOCIAL_BATCH_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0019_runtimedefaults_brand_palette_and_social_batch.py"
    RUNTIMEDEFAULTS_PORTAL_THEME_POLICY_BATCH_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0020_runtimedefaults_portal_theme_policy_batch.py"
    RUNTIMEDEFAULTS_THEME_SURFACE_BATCH_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0021_runtimedefaults_theme_surface_batch.py"
    RUNTIMEDEFAULTS_POLICY_RUNTIME_TOGGLES_BATCH_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0022_runtimedefaults_policy_runtime_toggles_batch.py"
    RUNTIMEDEFAULTS_REPORTS_THEMEPACK_BATCH_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0023_runtimedefaults_reports_themepack_batch.py"
    RUNTIMEDEFAULTS_POLICY_REPORTS_INTERVAL_BATCH_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0024_runtimedefaults_policy_reports_interval_batch.py"
    RUNTIMEDEFAULTS_POLICY_MAPS_COMPLIANCE_BATCH_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0025_runtimedefaults_policy_maps_and_compliance_batch.py"
    PHASE_B_SNAPSHOT_TYPED_METADATA_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0026_platformphasebdomainsnapshot_typed_metadata.py"
    PHASE_B_SNAPSHOT_KEY_CHECKSUMS_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0027_platformphasebdomainsnapshot_key_checksums.py"
    RUNTIMEDEFAULTS_REPORT_DOWNLOADS_ENABLED_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0028_runtimedefaults_report_downloads_enabled.py"
    RUNTIMEDEFAULTS_SMS_API_KEY_FIRST_CLASS_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0029_runtimedefaults_sms_api_key_first_class.py"
    RUNTIMEDEFAULTS_AI_PROVIDER_API_KEY_FIRST_CLASS_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0030_runtimedefaults_ai_provider_api_key_first_class.py"
    RUNTIMEDEFAULTS_WHATSAPP_API_TOKEN_FIRST_CLASS_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0031_runtimedefaults_whatsapp_api_token_first_class.py"
    RUNTIMEDEFAULTS_MARKSHEET_OCR_API_KEY_FIRST_CLASS_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0032_runtimedefaults_marksheet_ocr_api_key_first_class.py"
    RUNTIMEDEFAULTS_SMTP_PASSWORD_FIRST_CLASS_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0033_runtimedefaults_smtp_password_first_class.py"
    RUNTIMEDEFAULTS_WEBHOOK_SIGNING_SECRET_FIRST_CLASS_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0034_runtimedefaults_webhook_signing_secret_first_class.py"
    PLATFORM_INTEGRATION_WEBHOOK_EVENT_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0035_platform_integration_webhook_event.py"
    PLATFORM_REPORT_PLATFORM_SKU_DEFAULT_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0036_platform_report_platform_sku_default.py"
    RUNTIMEDEFAULTS_MARKETPLACE_PARTNER_CLIENT_SECRET_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0037_runtimedefaults_marketplace_partner_client_secret_first_class.py"
    PLATFORM_OPERATOR_PLAYBOOK_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0038_platform_operator_playbook_link.py"
    PLATFORM_OPERATOR_TRUTH_HUB_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0039_platform_operator_truth_hub_link.py"
    PLATFORM_OPERATOR_PHASE_B_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0040_platform_operator_phase_b_link.py"
    PLATFORM_OPERATOR_WORKFLOW_SIMULATOR_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0041_platform_operator_workflow_simulator_link.py"
    PLATFORM_OPERATOR_SUPPORT_DASHBOARD_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0042_platform_operator_support_dashboard_link.py"
    PLATFORM_OPERATOR_TENANT_HEALTH_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0043_platform_operator_tenant_health_link.py"
    PLATFORM_OPERATOR_COMMAND_CENTER_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0044_platform_operator_command_center_link.py"
    PLATFORM_OPERATOR_ORCHESTRATION_WORKBENCH_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0045_platform_operator_orchestration_workbench_link.py"
    PLATFORM_OPERATOR_SUPER_DASHBOARD_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0046_platform_operator_super_dashboard_link.py"
    PLATFORM_OPERATOR_SUPER_SCHOOLS_LIST_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0047_platform_operator_super_schools_list_link.py"
    PLATFORM_OPERATOR_SUPER_ANALYTICS_OVERVIEW_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0048_platform_operator_super_analytics_overview_link.py"
    PLATFORM_OPERATOR_PLATFORM_HUB_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0049_platform_operator_platform_hub_link.py"
    PLATFORM_OPERATOR_MIGRATION_CLOUD_LINK_MIGRATION = ROOT / "apps" / "platform_runtime" / "migrations" / "0050_platform_operator_migration_cloud_link.py"


def _run_check(
    cmd: list[str],
    label: str,
    *,
    timeout: int,
) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return f"{label} timed out after {timeout}s:\n{exc.stdout or ''}{exc.stderr or ''}"
    if proc.returncode != 0:
        return f"{label} failed:\n{proc.stdout or ''}{proc.stderr or ''}"
    return None


def main(argv: list[str] | None = None) -> int:
    try:
        _configure_root(_resolve_base(parse_args(argv).base))
    except ValueError as exc:
        print(f"Phase 5 siteconfig verification FAILED: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    for path, label in REQUIRED_DOCS:
        if not path.is_file():
            errors.append(f"Missing doc ({label}): {path.relative_to(ROOT)}")
        elif path.stat().st_size < 80:
            errors.append(f"Doc too small ({label}): {path.relative_to(ROOT)}")

    if not DOMAIN_OWNERSHIP_PY.is_file():
        errors.append(f"Missing {DOMAIN_OWNERSHIP_PY.relative_to(ROOT)}")
    else:
        text = DOMAIN_OWNERSHIP_PY.read_text(encoding="utf-8", errors="replace")
        for needle in ("classify_site_settings_field", "EXACT_FIELD_OWNERS", "PREFIX_FIELD_OWNERS"):
            if needle not in text:
                errors.append(f"domain_ownership.py missing {needle!r}")

    if not LINT_SCRIPT.is_file():
        errors.append("scripts/lint_tenant_settings.py not found")
    else:
        if err := _run_check(
            [sys.executable, str(LINT_SCRIPT), "--check-get-solo-only", "--base", str(ROOT)],
            "lint_tenant_settings --check-get-solo-only",
            timeout=120,
        ):
            errors.append(err)
        if err := _run_check(
            [
                sys.executable,
                str(LINT_SCRIPT),
                "--check-sitesettings-orm-in-tenant-apps",
                "--base",
                str(ROOT),
            ],
            "lint_tenant_settings --check-sitesettings-orm-in-tenant-apps",
            timeout=120,
        ):
            errors.append(err)

    verify_exact_storage = ROOT / "scripts" / "verify_domain_ownership_exact_storage.py"
    if not verify_exact_storage.is_file():
        errors.append(
            "scripts/verify_domain_ownership_exact_storage.py missing "
            "(EXACT_FIELD_OWNERS ↔ RuntimeDefaults first-class registry gate)."
        )
    elif err := _run_check(
        [sys.executable, str(verify_exact_storage), "--base", str(ROOT)],
        "verify_domain_ownership_exact_storage",
        timeout=60,
    ):
        errors.append(err)

    if not PHASE_B_BATCH0_MIGRATION.is_file():
        errors.append(
            "Phase B Batch 0 migration missing: "
            f"{PHASE_B_BATCH0_MIGRATION.relative_to(ROOT)} "
            "(see docs/SITECONFIG_OWNERSHIP_MIGRATION.md Phase B batch progress)."
        )

    if not PHASE_B_BATCH1_MIGRATION.is_file():
        errors.append(
            "Phase B Batch 1 migration missing: "
            f"{PHASE_B_BATCH1_MIGRATION.relative_to(ROOT)} "
            "(PlatformGlobalBranding singleton)."
        )

    if not PHASE_B_DOMAIN_SNAPSHOT_MIGRATION.is_file():
        errors.append(
            "Phase B domain snapshot migration missing: "
            f"{PHASE_B_DOMAIN_SNAPSHOT_MIGRATION.relative_to(ROOT)}"
        )

    if not RUNTIMEDEFAULTS_FIRST_CLASS_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults first-class columns migration missing: "
            f"{RUNTIMEDEFAULTS_FIRST_CLASS_MIGRATION.relative_to(ROOT)}"
        )

    if not PHASE_B_BATCH3_MIGRATION.is_file():
        errors.append(
            "Phase B Batch 3 migration missing: "
            f"{PHASE_B_BATCH3_MIGRATION.relative_to(ROOT)} "
            "(drop mirrored SiteSettings branding columns)."
        )

    if not RUNTIMEDEFAULTS_META_DOMAIN_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults meta_description/branded_domain migration missing: "
            f"{RUNTIMEDEFAULTS_META_DOMAIN_MIGRATION.relative_to(ROOT)}"
        )

    if not RUNTIMEDEFAULTS_TAGLINE_SCHOOL_CODE_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults tagline/school_code migration missing: "
            f"{RUNTIMEDEFAULTS_TAGLINE_SCHOOL_CODE_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_COMPANY_IDENTITY_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults company identity migration missing: "
            f"{RUNTIMEDEFAULTS_COMPANY_IDENTITY_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_IDENTITY_GEO_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults identity/geo migration missing: "
            f"{RUNTIMEDEFAULTS_IDENTITY_GEO_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_REGISTRY_STRINGS_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults registry strings migration missing: "
            f"{RUNTIMEDEFAULTS_REGISTRY_STRINGS_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_ADMISSION_ADMIN_PORTAL_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults admission/admin-portal migration missing: "
            f"{RUNTIMEDEFAULTS_ADMISSION_ADMIN_PORTAL_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_BRAND_RUNTIME_DASHBOARD_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults brand/runtime dashboard migration missing: "
            f"{RUNTIMEDEFAULTS_BRAND_RUNTIME_DASHBOARD_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_PORTAL_FEED_BATCH_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults portal-feed batch migration missing: "
            f"{RUNTIMEDEFAULTS_PORTAL_FEED_BATCH_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_BRAND_PALETTE_SOCIAL_BATCH_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults brand palette/social batch migration missing: "
            f"{RUNTIMEDEFAULTS_BRAND_PALETTE_SOCIAL_BATCH_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_PORTAL_THEME_POLICY_BATCH_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults portal/theme policy batch migration missing: "
            f"{RUNTIMEDEFAULTS_PORTAL_THEME_POLICY_BATCH_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_THEME_SURFACE_BATCH_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults theme-surface batch migration missing: "
            f"{RUNTIMEDEFAULTS_THEME_SURFACE_BATCH_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_POLICY_RUNTIME_TOGGLES_BATCH_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults policy/runtime toggles batch migration missing: "
            f"{RUNTIMEDEFAULTS_POLICY_RUNTIME_TOGGLES_BATCH_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_REPORTS_THEMEPACK_BATCH_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults reports/themepack batch migration missing: "
            f"{RUNTIMEDEFAULTS_REPORTS_THEMEPACK_BATCH_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_POLICY_REPORTS_INTERVAL_BATCH_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults policy/reports/interval batch migration missing: "
            f"{RUNTIMEDEFAULTS_POLICY_REPORTS_INTERVAL_BATCH_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_POLICY_MAPS_COMPLIANCE_BATCH_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults policy maps/compliance batch migration missing: "
            f"{RUNTIMEDEFAULTS_POLICY_MAPS_COMPLIANCE_BATCH_MIGRATION.relative_to(ROOT)}"
        )
    if not PHASE_B_SNAPSHOT_TYPED_METADATA_MIGRATION.is_file():
        errors.append(
            "Phase B snapshot typed metadata migration missing: "
            f"{PHASE_B_SNAPSHOT_TYPED_METADATA_MIGRATION.relative_to(ROOT)}"
        )
    if not PHASE_B_SNAPSHOT_KEY_CHECKSUMS_MIGRATION.is_file():
        errors.append(
            "Phase B snapshot key checksums migration missing: "
            f"{PHASE_B_SNAPSHOT_KEY_CHECKSUMS_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_REPORT_DOWNLOADS_ENABLED_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults report_downloads_enabled migration missing: "
            f"{RUNTIMEDEFAULTS_REPORT_DOWNLOADS_ENABLED_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_SMS_API_KEY_FIRST_CLASS_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults sms_api_key first-class migration missing: "
            f"{RUNTIMEDEFAULTS_SMS_API_KEY_FIRST_CLASS_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_AI_PROVIDER_API_KEY_FIRST_CLASS_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults ai_provider_api_key first-class migration missing: "
            f"{RUNTIMEDEFAULTS_AI_PROVIDER_API_KEY_FIRST_CLASS_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_WHATSAPP_API_TOKEN_FIRST_CLASS_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults whatsapp_api_token first-class migration missing: "
            f"{RUNTIMEDEFAULTS_WHATSAPP_API_TOKEN_FIRST_CLASS_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_MARKSHEET_OCR_API_KEY_FIRST_CLASS_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults marksheet_ocr_api_key first-class migration missing: "
            f"{RUNTIMEDEFAULTS_MARKSHEET_OCR_API_KEY_FIRST_CLASS_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_SMTP_PASSWORD_FIRST_CLASS_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults smtp_password first-class migration missing: "
            f"{RUNTIMEDEFAULTS_SMTP_PASSWORD_FIRST_CLASS_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_WEBHOOK_SIGNING_SECRET_FIRST_CLASS_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults webhook_signing_secret first-class migration missing: "
            f"{RUNTIMEDEFAULTS_WEBHOOK_SIGNING_SECRET_FIRST_CLASS_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_INTEGRATION_WEBHOOK_EVENT_MIGRATION.is_file():
        errors.append(
            "Platform integration webhook event migration missing: "
            f"{PLATFORM_INTEGRATION_WEBHOOK_EVENT_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_REPORT_PLATFORM_SKU_DEFAULT_MIGRATION.is_file():
        errors.append(
            "Platform report platform SKU default migration missing: "
            f"{PLATFORM_REPORT_PLATFORM_SKU_DEFAULT_MIGRATION.relative_to(ROOT)}"
        )
    if not RUNTIMEDEFAULTS_MARKETPLACE_PARTNER_CLIENT_SECRET_MIGRATION.is_file():
        errors.append(
            "RuntimeDefaults marketplace_partner_client_secret first-class migration missing: "
            f"{RUNTIMEDEFAULTS_MARKETPLACE_PARTNER_CLIENT_SECRET_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_PLAYBOOK_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorPlaybookLink migration missing: "
            f"{PLATFORM_OPERATOR_PLAYBOOK_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_TRUTH_HUB_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorTruthHubLink migration missing: "
            f"{PLATFORM_OPERATOR_TRUTH_HUB_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_PHASE_B_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorPhaseBLink migration missing: "
            f"{PLATFORM_OPERATOR_PHASE_B_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_WORKFLOW_SIMULATOR_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorWorkflowSimulatorLink migration missing: "
            f"{PLATFORM_OPERATOR_WORKFLOW_SIMULATOR_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_SUPPORT_DASHBOARD_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorSupportDashboardLink migration missing: "
            f"{PLATFORM_OPERATOR_SUPPORT_DASHBOARD_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_TENANT_HEALTH_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorTenantHealthLink migration missing: "
            f"{PLATFORM_OPERATOR_TENANT_HEALTH_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_COMMAND_CENTER_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorCommandCenterLink migration missing: "
            f"{PLATFORM_OPERATOR_COMMAND_CENTER_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_ORCHESTRATION_WORKBENCH_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorOrchestrationWorkbenchLink migration missing: "
            f"{PLATFORM_OPERATOR_ORCHESTRATION_WORKBENCH_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_SUPER_DASHBOARD_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorSuperDashboardLink migration missing: "
            f"{PLATFORM_OPERATOR_SUPER_DASHBOARD_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_SUPER_SCHOOLS_LIST_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorSuperSchoolsListLink migration missing: "
            f"{PLATFORM_OPERATOR_SUPER_SCHOOLS_LIST_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_SUPER_ANALYTICS_OVERVIEW_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorSuperAnalyticsOverviewLink migration missing: "
            f"{PLATFORM_OPERATOR_SUPER_ANALYTICS_OVERVIEW_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_PLATFORM_HUB_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorPlatformHubLink migration missing: "
            f"{PLATFORM_OPERATOR_PLATFORM_HUB_LINK_MIGRATION.relative_to(ROOT)}"
        )
    if not PLATFORM_OPERATOR_MIGRATION_CLOUD_LINK_MIGRATION.is_file():
        errors.append(
            "PlatformOperatorMigrationCloudLink migration missing: "
            f"{PLATFORM_OPERATOR_MIGRATION_CLOUD_LINK_MIGRATION.relative_to(ROOT)}"
        )

    inv = ROOT / "docs" / "site_settings_usage_inventory.md"
    if inv.is_file():
        lines = inv.read_text(encoding="utf-8", errors="replace").splitlines()[:30]
        status_line = next(
            (ln for ln in lines if ln.strip().startswith("**Status:**")), ""
        )
        if not status_line or (
            "DONE" not in status_line.upper()
            and "COMPLETE" not in status_line.upper()
        ):
            errors.append(
                "site_settings_usage_inventory.md must declare **Status:** DONE or COMPLETE "
                "(Phase 5 / §2.1 behavioral gate) in the header."
            )

    if errors:
        print("Phase 5 siteconfig verification FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "Phase 5 siteconfig verification OK (docs + domain_ownership + exact-storage registry "
        "+ get_solo + ORM lint + Phase B Batch 0-1 + Batch 3 + Batches 4-13 + "
        "RuntimeDefaults 0009-0035 + 0036-0050 platform_runtime migration artifacts)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
