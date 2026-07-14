#!/usr/bin/env python3
"""Six-phase tenant lifecycle audit.

This is a file-backed, read-only audit for the tenant journey:

1. Discovery, evaluation, signup, provisioning, isolation.
2. Configuration, branding, localization, rules, integrations.
3. Data migration and ingestion.
4. Steady-state operations.
5. Maintenance, scaling, tenant audit/support.
6. Offboarding, export, suspension, purge.

The point is not to prove every branch by marker hunting. It creates an
evidence ledger that blocks completion claims when tenant destinations,
Migration Cloud, blueprints, app catalog, or offboarding proof are not wired.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "generated"
JSON_OUT = OUT_DIR / "tenant_lifecycle_six_phase_audit.json"
MD_OUT = OUT_DIR / "tenant_lifecycle_six_phase_audit.md"


@dataclass(frozen=True)
class Probe:
    key: str
    phase: str
    relpath: str
    token: str
    severity: str = "high"
    note: str = ""
    invert: bool = False


PHASES = {
    "phase_1_discovery_evaluation_provisioning": "Discovery, evaluation, signup, provisioning, isolation",
    "phase_2_configuration_initialization": "Configuration, branding, localization, rules, integrations",
    "phase_3_migration_ingestion": "Data migration and ingestion",
    "phase_4_steady_state_operations": "Steady-state school operations",
    "phase_5_maintenance_evolution": "Maintenance, scaling, tenant audit, support",
    "phase_6_offboarding_deprovisioning": "Offboarding, export, suspension, purge",
    "tenant_operator_separation": "Tenant/operator separation",
    "truth_and_redundancy": "Truth ledger and redundancy control",
}


PROBES = [
    # Phase 1: public signup, verification, provisioning, isolation.
    Probe("public_signup_route", "phase_1_discovery_evaluation_provisioning", "config/public_urls.py", "path(\"signup/\", signup_school",
          note="Public host must expose self-service signup."),
    Probe("signup_slug_check_route", "phase_1_discovery_evaluation_provisioning", "config/public_urls.py", "signup/slug-check/",
          note="Prospects need live subdomain/workspace availability."),
    Probe("signup_verification_route", "phase_1_discovery_evaluation_provisioning", "config/public_urls.py", "verify-signup/",
          note="Email verification must be in the lifecycle."),
    Probe("signup_captures_plan", "phase_1_discovery_evaluation_provisioning", "apps/schools/signup_views.py", "plan_slug",
          note="Subscription/package intent must be captured before provisioning."),
    Probe("signup_captures_migration_intent", "phase_1_discovery_evaluation_provisioning", "apps/schools/signup_views.py", "migration_intent",
          note="Migration Cloud handoff should begin at signup when needed."),
    Probe("signup_assigns_data_residency", "phase_1_discovery_evaluation_provisioning", "apps/schools/signup_views.py", "apply_data_residency_for_new_school",
          note="Tenant data location cannot be fake or implicit."),
    Probe("provisioning_schema_client", "phase_1_discovery_evaluation_provisioning", "apps/schools/onboarding_service.py", "ensure_tenant_client_for_school",
          note="Provisioning must create/bind isolated tenant runtime."),
    Probe("provisioning_kill_switch", "phase_1_discovery_evaluation_provisioning", "apps/schools/onboarding_service.py", "kill_switch_on_failure",
          note="Failed provisioning must not leave a half-created tenant without audit."),
    Probe("tenant_admin_route", "phase_1_discovery_evaluation_provisioning", "config/tenant_urls.py", 'path("admin/", tenant_admin_site.urls)',
          note="Tenant backend admin must be tenant-owned, not operator admin."),
    Probe("provisioning_status_route", "phase_1_discovery_evaluation_provisioning", "config/tenant_urls.py", "tenant_provisioning_status",
          note="Tenant must see provisioning status."),

    # Phase 2: configuration, branding, localization, system rules, integrations.
    Probe("tenant_configuration_route", "phase_2_configuration_initialization", "config/tenant_urls.py", 'path("school/configuration/", school_configuration_center',
          note="Tenant configuration center must have a canonical tenant route."),
    Probe("tenant_onboarding_route", "phase_2_configuration_initialization", "apps/siteconfig/urls.py", "onboarding",
          note="Setup/onboarding checklist must be mounted."),
    Probe("theme_experience_preview", "phase_2_configuration_initialization", "templates/admin/components/theme_preview_section.html", "Role dashboard",
          note="Branding changes must preview role surfaces, not just color fields."),
    Probe("palette_preview_surface", "phase_2_configuration_initialization", "templates/admin/components/theme_preview_section.html", "preview-status-table",
          note="Palette preview must cover status/table/form/page states."),
    Probe("school_config_sections", "phase_2_configuration_initialization", "apps/platform_runtime/administration_catalog.py", "TENANT_CONFIGURATION_SECTIONS",
          note="Tenant-visible configuration sections must be explicit."),
    Probe("regional_localization_service", "phase_2_configuration_initialization", "apps/siteconfig/country_localization_service.py", "resolve_country_pack",
          note="Timezone, calendar, language, and regional defaults must be catalog-driven."),
    Probe("academic_year_lifecycle", "phase_2_configuration_initialization", "apps/academics/tests/test_academic_year_setup_lifecycle.py", "academic_year",
          note="Academic year/term setup needs test coverage."),
    Probe("integration_catalog", "phase_2_configuration_initialization", "apps/siteconfig/integration_catalog.py", "integration",
          note="Third-party integrations should be cataloged."),

    # Phase 3: Migration Cloud and ingestion.
    Probe("tenant_migration_cloud_route", "phase_3_migration_ingestion", "config/tenant_urls.py", '"school/setup/migration-cloud/"',
          note="Tenant Migration Cloud must be reachable on tenant host."),
    Probe("tenant_upload_surface", "phase_3_migration_ingestion", "apps/migration_cloud/views_tenant_upload.py", "TenantMigrationUploadView",
          note="Tenants need a direct file-first migration path."),
    Probe("tenant_upload_tenant_scoped", "phase_3_migration_ingestion", "apps/migration_cloud/views_tenant_upload.py", "_tenant_bundle_or_404",
          note="Migration bundle access must be tenant-scoped."),
    Probe("tenant_upload_progress", "phase_3_migration_ingestion", "apps/migration_cloud/views_tenant_upload.py", "TenantMigrationProgressView",
          note="Migration processing must not feel blank or stalled."),
    Probe("tenant_upload_repair", "phase_3_migration_ingestion", "apps/migration_cloud/views_tenant_upload.py", "TenantMigrationRepairView",
          note="Failed/incomplete imports need safe idempotent repair."),
    Probe("migration_control_totals", "phase_3_migration_ingestion", "templates/migration_cloud/intake_new.html", "expected_students_count",
          note="Migration Cloud must support control totals for baseline proof."),
    Probe("migration_post_apply_verification", "phase_3_migration_ingestion", "apps/migration_cloud/verification.py", "verify",
          note="Go-live baseline cannot rely on upload success alone."),
    Probe("csv_import_verifier", "phase_3_migration_ingestion", "scripts/verify_tenant_onboarding_csv_import.py", "TENANT_ONBOARDING_CSV_IMPORT",
          note="Tenant CSV path needs a verifier."),

    # Phase 4: daily operations, RBAC, app consumption, offline.
    Probe("tenant_dashboard_route", "phase_4_steady_state_operations", "config/tenant_urls.py", '"backend/"',
          note="Tenant daily backend route must exist."),
    Probe("user_role_provisioning", "phase_4_steady_state_operations", "apps/accounts/permissions.py", "tenant_operator_hub_eligible",
          note="Tenant admins need scoped role access control."),
    Probe("finance_operations_route", "phase_4_steady_state_operations", "config/tenant_urls.py", "finance",
          note="Daily tuition/payment work must be tenant-routed."),
    Probe("communications_route", "phase_4_steady_state_operations", "config/tenant_urls.py", "communication",
          note="School announcements/messages must be tenant-routed."),
    Probe("academics_route", "phase_4_steady_state_operations", "config/tenant_urls.py", "academics",
          note="Attendance, classes, gradebook, and reports must be tenant-routed."),
    Probe("workflow_center_route", "phase_4_steady_state_operations", "config/tenant_urls.py", '"school/workflows/"',
          note="Tenant workflow destination must stay tenant-scoped."),
    Probe("tenant_app_catalog_route", "phase_4_steady_state_operations", "config/tenant_urls.py", '"settings/app-catalog/"',
          note="Feature/app consumption must be tenant-visible."),
    Probe("offline_db", "phase_4_steady_state_operations", "static/js/offline-db.js", "school_readiness",
          note="Local-first/offline-first tenant operation must have client storage."),
    Probe("offline_action_handlers", "phase_4_steady_state_operations", "apps/schools/offline_workflow_handlers.py", "offline",
          note="Offline actions need server replay handlers."),

    # Phase 5: maintenance and evolution.
    Probe("subscription_scaling", "phase_5_maintenance_evolution", "apps/billing/tasks_billing_lifecycle.py", "subscription",
          note="Scaling and package lifecycle must be represented."),
    Probe("payment_readiness", "phase_5_maintenance_evolution", "apps/finance/views_payment_readiness_dashboard.py", "payment_readiness_dashboard",
          note="Payment posture must be honest and visible."),
    Probe("tenant_audit_surface", "phase_5_maintenance_evolution", "templates/compliance/dashboard.html", "Audit Trail",
          note="Schools need internal audit visibility."),
    Probe("support_surface", "phase_5_maintenance_evolution", "config/tenant_urls.py", "feedback",
          note="Tenant support must stay tenant-contextual."),
    Probe("change_request_governance", "phase_5_maintenance_evolution", "apps/platform_runtime/configuration_change_requests.py", "ConfigurationChangeRequest",
          note="Tenant config changes need preview/approval/schedule paths."),
    Probe("app_install_lifecycle", "phase_5_maintenance_evolution", "apps/marketplace/lifecycle.py", "install",
          note="App catalog installs need a real lifecycle."),
    Probe("tenant_health_signals", "phase_5_maintenance_evolution", "apps/platform_runtime/tests/test_tenant_lifecycle_health_signals.py", "health",
          note="Maintenance needs health signals and test coverage."),

    # Phase 6: offboarding.
    Probe("tenant_offboarding_route", "phase_6_offboarding_deprovisioning", "config/tenant_urls.py", "tenant_offboarding_page",
          note="Tenant self-service offboarding page must exist."),
    Probe("tenant_offboarding_export_api", "phase_6_offboarding_deprovisioning", "config/tenant_urls.py", "tenant_offboarding_export_download",
          note="Data extraction/download must be tenant-facing."),
    Probe("tenant_wind_down", "phase_6_offboarding_deprovisioning", "apps/lifecycle/wind_down.py", "apply_wind_down_mode",
          note="Suspension/read-only posture must be explicit."),
    Probe("commerce_wind_down_guard", "phase_6_offboarding_deprovisioning", "apps/lifecycle/wind_down_guards.py", "block_if_wind_down_commerce",
          note="Wind-down must block new commerce/enrollment writes."),
    Probe("offboarding_inventory", "phase_6_offboarding_deprovisioning", "apps/compliance/tenant_offboarding_inventory.py", "tenant",
          note="Purge must know what tenant assets/data exist."),
    Probe("offboarding_purge_ops", "phase_6_offboarding_deprovisioning", "apps/lifecycle/purge_operations.py", "Purge",
          note="Hard deletion must have auditable operations."),
    Probe("operator_only_purge", "phase_6_offboarding_deprovisioning", "apps/schools/tenant_offboarding_policy.py", "operator_only_offboarding",
          note="Dangerous purge controls remain operator-approved, not hidden fake tenant buttons."),
    Probe("backup_purge_honesty", "phase_6_offboarding_deprovisioning", "docs/generated/tenant_lifecycle_forensic_gap_audit.md", "Postgres",
          note="Backup/schema purge proof must not be claimed green on SQLite only."),

    # Separation and truth.
    Probe("tenant_no_operator_super_links", "tenant_operator_separation", "templates/siteconfig/partials/get_blueprints_body.html", "/super/", invert=True,
          note="Tenant blueprint catalog must not expose operator links."),
    Probe("tenant_no_operator_blueprint_config_links", "tenant_operator_separation", "templates/siteconfig/partials/get_blueprints_body.html", "/configuration/blueprints/", invert=True,
          note="Tenant blueprint catalog must not expose operator configuration paths."),
    Probe("tenant_admin_separate_site", "tenant_operator_separation", "config/admin.py", "tenant_admin_site = TenantAdminSite",
          note="Tenant admin site must be separate from platform admin site."),
    Probe("platform_admin_separate_site", "tenant_operator_separation", "config/admin.py", "platform_admin_site = PlatformAdminSite",
          note="Operator admin site must be separate from tenant admin site."),
    Probe("tenant_admin_denies_platform_host", "tenant_operator_separation", "config/admin.py", "self._is_platform_host(request)",
          note="Tenant admin must deny platform-host access."),
    Probe("tenant_configuration_forbidden", "tenant_operator_separation", "apps/platform_runtime/views_administration.py", "tenant_configuration_forbidden",
          note="Tenant cannot use platform configuration root."),
    Probe("no_fake_payment_copy", "truth_and_redundancy", "templates/finance/payment_readiness_dashboard.html", "No fake",
          note="Payment readiness must be honest about external PSP blockers."),
    Probe("blueprint_truth_audit", "truth_and_redundancy", "docs/generated/blueprint_local_first_offline_audit.json", '"overall_status"',
          note="Blueprint truth ledger must exist."),
    Probe("migration_truth_audit", "truth_and_redundancy", "docs/generated/migration_cloud_connector_discovery.json", '"tenant_routes"',
          note="Migration Cloud connector discovery must be generated evidence."),
]


ROUTE_CHECKS = (
    ("public_signup", "signup_school", None, "config.public_urls"),
    ("public_verify_signup", "verify_signup", None, "config.public_urls"),
    ("tenant_provisioning_status", "tenant_provisioning_status", None, "config.tenant_urls"),
    ("tenant_configuration", "school_configuration_center_canonical", None, "config.tenant_urls"),
    ("tenant_blueprints", "tenant_blueprint_setup", None, "config.tenant_urls"),
    ("tenant_packs", "tenant_pack_setup", None, "config.tenant_urls"),
    ("tenant_imports", "school_setup_imports", None, "config.tenant_urls"),
    ("tenant_migration_cloud", "migration_cloud_connector:connector-home", None, "config.tenant_urls"),
    ("tenant_migration_upload", "migration_cloud_connector:upload", None, "config.tenant_urls"),
    ("tenant_app_catalog", "tenant_app_catalog", None, "config.tenant_urls"),
    ("tenant_offboarding", "tenant_offboarding", None, "config.tenant_urls"),
)


GATE_SCRIPTS = (
    "scripts/audit_tenant_lifecycle_aggressive.py",
    "scripts/verify_tenant_lifecycle_unified.py",
    "scripts/verify_migration_cloud_intake_experience.py",
    "scripts/audit_blueprint_local_first_offline.py",
)


def _read(relpath: str) -> str:
    path = ROOT / relpath
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _probe_result(probe: Probe) -> dict[str, Any]:
    text = _read(probe.relpath)
    exists = bool(text)
    contains = probe.token in text if exists else False
    passed = (not contains) if probe.invert else contains
    return {
        **asdict(probe),
        "exists": exists,
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
    }


def _setup_django() -> list[str]:
    failures: list[str] = []
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ.setdefault("SECRET_KEY", "audit-secret-key")
    try:
        import django

        django.setup()
    except Exception as exc:  # noqa: BLE001
        failures.append(f"django.setup failed: {type(exc).__name__}: {exc}")
    return failures


def _route_results() -> list[dict[str, Any]]:
    failures = _setup_django()
    if failures:
        return [
            {
                "key": "django_setup",
                "name": "",
                "urlconf": "",
                "passed": False,
                "status": "FAIL",
                "url": "",
                "failure": "; ".join(failures),
            }
        ]
    from django.urls import reverse

    rows: list[dict[str, Any]] = []
    for key, name, kwargs, urlconf in ROUTE_CHECKS:
        try:
            url = reverse(name, kwargs=kwargs or {}, urlconf=urlconf)
            bad_target = url.startswith("/super/") or url.startswith("/configuration/")
            rows.append(
                {
                    "key": key,
                    "name": name,
                    "urlconf": urlconf,
                    "passed": not bad_target,
                    "status": "PASS" if not bad_target else "FAIL",
                    "url": url,
                    "failure": "tenant route points to operator path" if bad_target else "",
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "key": key,
                    "name": name,
                    "urlconf": urlconf,
                    "passed": False,
                    "status": "FAIL",
                    "url": "",
                    "failure": f"{type(exc).__name__}: {exc}",
                }
            )
    return rows


def _run_gate(script: str) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return {
        "script": script,
        "exit": proc.returncode,
        "passed": proc.returncode == 0,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "output_tail": out[-1200:],
    }


def _worktree_drift() -> dict[str, Any]:
    canonical = ROOT.parent / "school-management-system"
    rows: list[dict[str, Any]] = []
    for label, path in (("active", ROOT), ("canonical_local", canonical)):
        if not (path / ".git").exists():
            rows.append({"label": label, "path": str(path), "git": False})
            continue
        proc = subprocess.run(
            ["git", "status", "-sb"],
            cwd=str(path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        log = subprocess.run(
            ["git", "log", "--oneline", "-1", "--decorate"],
            cwd=str(path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        rows.append(
            {
                "label": label,
                "path": str(path),
                "git": True,
                "status": (proc.stdout or proc.stderr).strip(),
                "head": (log.stdout or log.stderr).strip(),
            }
        )
    warnings: list[str] = []
    if len(rows) == 2 and rows[0].get("head") and rows[1].get("head") and rows[0]["head"] != rows[1]["head"]:
        warnings.append("active render-audit worktree and canonical school-management-system worktree are on different commits")
    if len(rows) == 2 and "behind" in rows[1].get("status", ""):
        warnings.append("canonical local school-management-system worktree is behind origin/main")
    if len(rows) == 2 and (" M " in rows[1].get("status", "") or "\n?? " in rows[1].get("status", "")):
        warnings.append("canonical local school-management-system worktree has uncommitted changes")
    return {"rows": rows, "warnings": warnings}


def _payload() -> dict[str, Any]:
    probe_rows = [_probe_result(probe) for probe in PROBES]
    route_rows = _route_results()
    gate_rows = [_run_gate(script) for script in GATE_SCRIPTS]
    drift = _worktree_drift()

    phase_summary: dict[str, dict[str, Any]] = {}
    for key, label in PHASES.items():
        rows = [row for row in probe_rows if row["phase"] == key]
        total = len(rows)
        passed = sum(1 for row in rows if row["passed"])
        phase_summary[key] = {
            "label": label,
            "passed": passed,
            "total": total,
            "status": "PASS" if total and passed == total else "FAIL",
            "failed": [row["key"] for row in rows if not row["passed"]],
        }

    failures = [
        f"probe:{row['key']}"
        for row in probe_rows
        if not row["passed"] and row["severity"] in {"critical", "high"}
    ]
    failures.extend(f"route:{row['key']}" for row in route_rows if not row["passed"])
    failures.extend(f"gate:{row['script']}" for row in gate_rows if not row["passed"])

    overall = "PASS" if not failures else "FAIL"
    if overall == "PASS" and drift["warnings"]:
        overall = "PASS_WITH_WORKTREE_WARNINGS"

    return {
        "audit": "tenant_lifecycle_six_phase",
        "scope": "tenant lifecycle from discovery through offboarding, with Migration Cloud and tenant/operator separation",
        "overall_status": overall,
        "phase_summary": phase_summary,
        "probes": probe_rows,
        "routes": route_rows,
        "gates": gate_rows,
        "worktree_drift": drift,
        "failure_count": len(failures),
        "failures": failures,
        "interpretation": [
            "PASS means repo-side lifecycle wiring is present and focused gates pass.",
            "PASS_WITH_WORKTREE_WARNINGS means repo-side wiring passes, but local worktree drift can explain deployment confusion.",
            "This audit does not claim external vendor readiness, production PostgreSQL/RLS proof, or real DNS/email/PSP completion unless separate environment evidence exists.",
        ],
    }


def _write_json(payload: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_md(payload: dict[str, Any]) -> None:
    lines = [
        "# Tenant Lifecycle Six-Phase Audit",
        "",
        f"Overall status: `{payload['overall_status']}`",
        "",
        "## Phase Summary",
        "",
        "| Phase | Status | Passing | Failed checks |",
        "| --- | --- | ---: | --- |",
    ]
    for key, row in payload["phase_summary"].items():
        failed = ", ".join(f"`{item}`" for item in row["failed"]) or "None"
        lines.append(
            f"| {row['label']} | `{row['status']}` | {row['passed']} / {row['total']} | {failed} |"
        )
    lines.extend(["", "## Tenant Routes", "", "| Check | Status | URL | Failure |", "| --- | --- | --- | --- |"])
    for row in payload["routes"]:
        lines.append(
            f"| `{row['key']}` | `{row['status']}` | `{row.get('url') or ''}` | {row.get('failure') or ''} |"
        )
    lines.extend(["", "## Gates", "", "| Script | Status |", "| --- | --- |"])
    for row in payload["gates"]:
        lines.append(f"| `{row['script']}` | `{row['status']}` |")
    if payload["worktree_drift"]["warnings"]:
        lines.extend(["", "## Worktree Warnings", ""])
        for warning in payload["worktree_drift"]["warnings"]:
            lines.append(f"- {warning}")
    lines.extend(
        [
            "",
            "## Failed Probe Details",
            "",
        ]
    )
    failed_probes = [row for row in payload["probes"] if not row["passed"]]
    if not failed_probes:
        lines.append("None")
    else:
        for row in failed_probes:
            lines.append(
                f"- `{row['key']}` ({PHASES.get(row['phase'], row['phase'])}): `{row['relpath']}` missing/violates `{row['token']}`. {row['note']}"
            )
    lines.extend(["", "## Interpretation", ""])
    for item in payload["interpretation"]:
        lines.append(f"- {item}")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    payload = _payload()
    _write_json(payload)
    _write_md(payload)
    print(f"TENANT_LIFECYCLE_SIX_PHASE_AUDIT_{payload['overall_status']}")
    print(f"  json: {JSON_OUT.relative_to(ROOT)}")
    print(f"  md: {MD_OUT.relative_to(ROOT)}")
    return 0 if payload["overall_status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
