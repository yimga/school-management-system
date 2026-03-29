#!/usr/bin/env python3
"""
Phase B execution verification (batches 1+ wiring).

- Batch 0: still owned by verify_phase_5_siteconfig.py (0162 + lints).
- Batch 1: brand_experience.PlatformGlobalBranding migration exists; when a
  SiteSettings row exists, singleton pk=1 must exist after migrations.
- Batches 4-13: platform_runtime.PlatformPhaseBDomainSnapshot; when SiteSettings
  exists, one row per PHASE_B_SNAPSHOT_DOMAINS after migrations + save sync.

``migration_artifact_errors()`` and ``orm_phase_b_execution_errors()`` are importable
for in-process tests (migrated DB). ORM + **physical** ``siteconfig_sitesettings``
column check via ``sitesettings_slim_db_errors``. CLI: ``python scripts/verify_phase_b_execution.py``.

Exit 0 = OK; non-zero = fix migrations or backfill.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MIGRATION_0002 = (
    ROOT / "apps" / "brand_experience" / "migrations" / "0002_platform_global_branding.py"
)
MIGRATION_0007 = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0007_platform_phase_b_domain_snapshots.py"
)
MIGRATION_0036_REPORT_SKU_DEFAULT = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0036_platform_report_platform_sku_default.py"
)
MIGRATION_0038_OPERATOR_PLAYBOOK_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0038_platform_operator_playbook_link.py"
)
MIGRATION_0039_OPERATOR_TRUTH_HUB_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0039_platform_operator_truth_hub_link.py"
)
MIGRATION_0040_OPERATOR_PHASE_B_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0040_platform_operator_phase_b_link.py"
)
MIGRATION_0041_OPERATOR_WORKFLOW_SIMULATOR_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0041_platform_operator_workflow_simulator_link.py"
)
MIGRATION_0042_OPERATOR_SUPPORT_DASHBOARD_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0042_platform_operator_support_dashboard_link.py"
)
MIGRATION_0043_OPERATOR_TENANT_HEALTH_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0043_platform_operator_tenant_health_link.py"
)
MIGRATION_0044_OPERATOR_COMMAND_CENTER_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0044_platform_operator_command_center_link.py"
)
MIGRATION_0045_OPERATOR_ORCHESTRATION_WORKBENCH_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0045_platform_operator_orchestration_workbench_link.py"
)
MIGRATION_0046_OPERATOR_SUPER_DASHBOARD_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0046_platform_operator_super_dashboard_link.py"
)
MIGRATION_0047_OPERATOR_SUPER_SCHOOLS_LIST_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0047_platform_operator_super_schools_list_link.py"
)
MIGRATION_0048_OPERATOR_SUPER_ANALYTICS_OVERVIEW_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0048_platform_operator_super_analytics_overview_link.py"
)
MIGRATION_0049_OPERATOR_PLATFORM_HUB_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0049_platform_operator_platform_hub_link.py"
)
MIGRATION_0050_OPERATOR_MIGRATION_CLOUD_LINK = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0050_platform_operator_migration_cloud_link.py"
)


def migration_artifact_errors() -> list[str]:
    """Repository-side checks (no Django required)."""
    errors: list[str] = []
    if not MIGRATION_0002.is_file():
        errors.append(
            f"Missing Phase B Batch 1 migration: {MIGRATION_0002.relative_to(ROOT)}"
        )
    if not MIGRATION_0007.is_file():
        errors.append(
            "Missing Phase B Batches 4-13 migration: "
            f"{MIGRATION_0007.relative_to(ROOT)}"
        )
    if not MIGRATION_0036_REPORT_SKU_DEFAULT.is_file():
        errors.append(
            "Missing platform_runtime report platform SKU default migration: "
            f"{MIGRATION_0036_REPORT_SKU_DEFAULT.relative_to(ROOT)}"
        )
    if not MIGRATION_0038_OPERATOR_PLAYBOOK_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator playbook link migration: "
            f"{MIGRATION_0038_OPERATOR_PLAYBOOK_LINK.relative_to(ROOT)}"
        )
    if not MIGRATION_0039_OPERATOR_TRUTH_HUB_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator truth hub link migration: "
            f"{MIGRATION_0039_OPERATOR_TRUTH_HUB_LINK.relative_to(ROOT)}"
        )
    if not MIGRATION_0040_OPERATOR_PHASE_B_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator Phase B link migration: "
            f"{MIGRATION_0040_OPERATOR_PHASE_B_LINK.relative_to(ROOT)}"
        )
    if not MIGRATION_0041_OPERATOR_WORKFLOW_SIMULATOR_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator workflow simulator link migration: "
            f"{MIGRATION_0041_OPERATOR_WORKFLOW_SIMULATOR_LINK.relative_to(ROOT)}"
        )
    if not MIGRATION_0042_OPERATOR_SUPPORT_DASHBOARD_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator support dashboard link migration: "
            f"{MIGRATION_0042_OPERATOR_SUPPORT_DASHBOARD_LINK.relative_to(ROOT)}"
        )
    if not MIGRATION_0043_OPERATOR_TENANT_HEALTH_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator tenant health link migration: "
            f"{MIGRATION_0043_OPERATOR_TENANT_HEALTH_LINK.relative_to(ROOT)}"
        )
    if not MIGRATION_0044_OPERATOR_COMMAND_CENTER_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator command center link migration: "
            f"{MIGRATION_0044_OPERATOR_COMMAND_CENTER_LINK.relative_to(ROOT)}"
        )
    if not MIGRATION_0045_OPERATOR_ORCHESTRATION_WORKBENCH_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator orchestration workbench link migration: "
            f"{MIGRATION_0045_OPERATOR_ORCHESTRATION_WORKBENCH_LINK.relative_to(ROOT)}"
        )
    if not MIGRATION_0046_OPERATOR_SUPER_DASHBOARD_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator super dashboard link migration: "
            f"{MIGRATION_0046_OPERATOR_SUPER_DASHBOARD_LINK.relative_to(ROOT)}"
        )
    if not MIGRATION_0047_OPERATOR_SUPER_SCHOOLS_LIST_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator super schools list link migration: "
            f"{MIGRATION_0047_OPERATOR_SUPER_SCHOOLS_LIST_LINK.relative_to(ROOT)}"
        )
    if not MIGRATION_0048_OPERATOR_SUPER_ANALYTICS_OVERVIEW_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator super analytics overview link migration: "
            f"{MIGRATION_0048_OPERATOR_SUPER_ANALYTICS_OVERVIEW_LINK.relative_to(ROOT)}"
        )
    if not MIGRATION_0049_OPERATOR_PLATFORM_HUB_LINK.is_file():
        errors.append(
            "Missing platform_runtime operator platform hub link migration: "
            f"{MIGRATION_0049_OPERATOR_PLATFORM_HUB_LINK.relative_to(ROOT)}"
        )
    return errors


def orm_phase_b_execution_errors() -> list[str]:
    """
    Database checks after django.setup() against the active default connection.
    Used by CLI and by Django tests (migrated test DB).
    """
    from django.apps import apps
    from django.db import connection

    errors: list[str] = []

    try:
        model = apps.get_model("brand_experience", "PlatformGlobalBranding")
        table_name = model._meta.db_table
        tables = connection.introspection.table_names()
        if table_name not in tables:
            errors.append(
                f"Table {table_name} missing - run migrations (brand_experience.0002)."
            )
    except Exception as exc:
        errors.append(f"Could not verify PlatformGlobalBranding table: {exc}")

    try:
        snap_model = apps.get_model("platform_runtime", "PlatformPhaseBDomainSnapshot")
        snap_table = snap_model._meta.db_table
        tables = connection.introspection.table_names()
        if snap_table not in tables:
            errors.append(
                f"Table {snap_table} missing - run migrations "
                "(platform_runtime.0007_platform_phase_b_domain_snapshots)."
            )
    except Exception as exc:
        errors.append(f"Could not verify PlatformPhaseBDomainSnapshot table: {exc}")

    try:
        sku_default_model = apps.get_model(
            "platform_runtime", "PlatformReportPlatformSkuDefault"
        )
        sku_table = sku_default_model._meta.db_table
        tables = connection.introspection.table_names()
        if sku_table not in tables:
            errors.append(
                f"Table {sku_table} missing - run migrations "
                "(platform_runtime.0036_platform_report_platform_sku_default)."
            )
    except Exception as exc:
        errors.append(f"Could not verify PlatformReportPlatformSkuDefault table: {exc}")

    try:
        playbook_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorPlaybookLink"
        )
        playbook_table = playbook_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if playbook_table not in tables:
            errors.append(
                f"Table {playbook_table} missing - run migrations "
                "(platform_runtime.0038_platform_operator_playbook_link)."
            )
    except Exception as exc:
        errors.append(f"Could not verify PlatformOperatorPlaybookLink table: {exc}")

    try:
        truth_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorTruthHubLink"
        )
        truth_table = truth_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if truth_table not in tables:
            errors.append(
                f"Table {truth_table} missing - run migrations "
                "(platform_runtime.0039_platform_operator_truth_hub_link)."
            )
    except Exception as exc:
        errors.append(f"Could not verify PlatformOperatorTruthHubLink table: {exc}")

    try:
        phase_b_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorPhaseBLink"
        )
        phase_b_table = phase_b_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if phase_b_table not in tables:
            errors.append(
                f"Table {phase_b_table} missing - run migrations "
                "(platform_runtime.0040_platform_operator_phase_b_link)."
            )
    except Exception as exc:
        errors.append(f"Could not verify PlatformOperatorPhaseBLink table: {exc}")

    try:
        wf_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorWorkflowSimulatorLink"
        )
        wf_table = wf_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if wf_table not in tables:
            errors.append(
                f"Table {wf_table} missing - run migrations "
                "(platform_runtime.0041_platform_operator_workflow_simulator_link)."
            )
    except Exception as exc:
        errors.append(
            f"Could not verify PlatformOperatorWorkflowSimulatorLink table: {exc}"
        )

    try:
        support_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorSupportDashboardLink"
        )
        support_table = support_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if support_table not in tables:
            errors.append(
                f"Table {support_table} missing - run migrations "
                "(platform_runtime.0042_platform_operator_support_dashboard_link)."
            )
    except Exception as exc:
        errors.append(
            f"Could not verify PlatformOperatorSupportDashboardLink table: {exc}"
        )

    try:
        th_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorTenantHealthLink"
        )
        th_table = th_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if th_table not in tables:
            errors.append(
                f"Table {th_table} missing - run migrations "
                "(platform_runtime.0043_platform_operator_tenant_health_link)."
            )
    except Exception as exc:
        errors.append(f"Could not verify PlatformOperatorTenantHealthLink table: {exc}")

    try:
        cc_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorCommandCenterLink"
        )
        cc_table = cc_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if cc_table not in tables:
            errors.append(
                f"Table {cc_table} missing - run migrations "
                "(platform_runtime.0044_platform_operator_command_center_link)."
            )
    except Exception as exc:
        errors.append(f"Could not verify PlatformOperatorCommandCenterLink table: {exc}")

    try:
        orch_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorOrchestrationWorkbenchLink"
        )
        orch_table = orch_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if orch_table not in tables:
            errors.append(
                f"Table {orch_table} missing - run migrations "
                "(platform_runtime.0045_platform_operator_orchestration_workbench_link)."
            )
    except Exception as exc:
        errors.append(
            f"Could not verify PlatformOperatorOrchestrationWorkbenchLink table: {exc}"
        )

    try:
        sd_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorSuperDashboardLink"
        )
        sd_table = sd_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if sd_table not in tables:
            errors.append(
                f"Table {sd_table} missing - run migrations "
                "(platform_runtime.0046_platform_operator_super_dashboard_link)."
            )
    except Exception as exc:
        errors.append(
            f"Could not verify PlatformOperatorSuperDashboardLink table: {exc}"
        )

    try:
        ssl_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorSuperSchoolsListLink"
        )
        ssl_table = ssl_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if ssl_table not in tables:
            errors.append(
                f"Table {ssl_table} missing - run migrations "
                "(platform_runtime.0047_platform_operator_super_schools_list_link)."
            )
    except Exception as exc:
        errors.append(
            f"Could not verify PlatformOperatorSuperSchoolsListLink table: {exc}"
        )

    try:
        sao_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorSuperAnalyticsOverviewLink"
        )
        sao_table = sao_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if sao_table not in tables:
            errors.append(
                f"Table {sao_table} missing - run migrations "
                "(platform_runtime.0048_platform_operator_super_analytics_overview_link)."
            )
    except Exception as exc:
        errors.append(
            f"Could not verify PlatformOperatorSuperAnalyticsOverviewLink table: {exc}"
        )

    try:
        ph_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorPlatformHubLink"
        )
        ph_table = ph_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if ph_table not in tables:
            errors.append(
                f"Table {ph_table} missing - run migrations "
                "(platform_runtime.0049_platform_operator_platform_hub_link)."
            )
    except Exception as exc:
        errors.append(
            f"Could not verify PlatformOperatorPlatformHubLink table: {exc}"
        )

    try:
        mc_link_model = apps.get_model(
            "platform_runtime", "PlatformOperatorMigrationCloudLink"
        )
        mc_table = mc_link_model._meta.db_table
        tables = connection.introspection.table_names()
        if mc_table not in tables:
            errors.append(
                f"Table {mc_table} missing - run migrations "
                "(platform_runtime.0050_platform_operator_migration_cloud_link)."
            )
    except Exception as exc:
        errors.append(
            f"Could not verify PlatformOperatorMigrationCloudLink table: {exc}"
        )

    try:
        from apps.siteconfig.models import SiteSettings
        from apps.brand_experience.models import PlatformGlobalBranding
        from apps.platform_runtime.models import PlatformPhaseBDomainSnapshot
        from apps.platform_runtime.phase_b_domain_snapshots import PHASE_B_SNAPSHOT_DOMAINS

        if SiteSettings.objects.exists():
            if not PlatformGlobalBranding.objects.filter(pk=1).exists():
                errors.append(
                    "SiteSettings row exists but PlatformGlobalBranding pk=1 missing - "
                    "run migrations (brand_experience.0002_platform_global_branding)."
                )
            missing_domains = [
                d
                for d in PHASE_B_SNAPSHOT_DOMAINS
                if not PlatformPhaseBDomainSnapshot.objects.filter(pk=d).exists()
            ]
            if missing_domains:
                errors.append(
                    "SiteSettings present but Phase B domain snapshots incomplete "
                    f"(missing: {', '.join(missing_domains)}). Save SiteSettings once or "
                    "re-run migration 0007 seed."
                )
    except Exception as exc:
        errors.append(f"ORM consistency check failed: {exc}")

    try:
        from django.db import connection

        from apps.siteconfig.sitesettings_slim_contract import (
            sitesettings_slim_db_errors,
            sitesettings_slim_model_errors,
        )

        errors.extend(sitesettings_slim_model_errors())
        errors.extend(sitesettings_slim_db_errors(connection))
    except Exception as exc:
        errors.append(f"SiteSettings slim contract check failed: {exc}")

    return errors


def main() -> int:
    errors = migration_artifact_errors()
    if errors:
        print("Phase B execution verification FAILED (artifacts):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    from django.conf import settings

    gate_file = (os.environ.get("DJANGO_TEST_DB_FILE") or "").strip()
    if gate_file and settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
        gpath = Path(gate_file)
        if not gpath.is_absolute():
            gpath = ROOT / gpath
        settings.DATABASES["default"]["NAME"] = str(gpath)

    django.setup()

    errors = orm_phase_b_execution_errors()
    if errors:
        print("Phase B execution verification FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "Phase B execution verification OK (Batch 1 PlatformGlobalBranding + "
        "Batches 4-13 PlatformPhaseBDomainSnapshot when SiteSettings present + "
        "PlatformReportPlatformSkuDefault + PlatformOperatorPlaybookLink + "
        "PlatformOperatorTruthHubLink + PlatformOperatorPhaseBLink + "
        "PlatformOperatorWorkflowSimulatorLink + "
        "PlatformOperatorSupportDashboardLink + "
        "PlatformOperatorTenantHealthLink + "
        "PlatformOperatorCommandCenterLink + "
        "PlatformOperatorOrchestrationWorkbenchLink + "
        "PlatformOperatorSuperDashboardLink + "
        "PlatformOperatorSuperSchoolsListLink + "
        "PlatformOperatorSuperAnalyticsOverviewLink + "
        "PlatformOperatorPlatformHubLink + "
        "PlatformOperatorMigrationCloudLink tables)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
