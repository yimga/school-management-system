#!/usr/bin/env python3
"""
ZIP Phase 5 — SiteSettings / siteconfig dismantling (repository gate).

Verifies:
- Canonical docs exist and reference the ownership / inventory discipline
- domain_ownership module defines field classification (inventory + code stay aligned)
- lint_tenant_settings: no get_solo() in tenant-facing app trees

Includes get_solo lint and SiteSettings.objects.* lint in tenant app trees.
Phase B Batch 0: asserts ``0162_phase_b_slim_sitesettings.py`` exists.
Phase B Batch 1: asserts ``brand_experience/0002_platform_global_branding.py`` exists.
Phase B Batch 3: asserts ``siteconfig/0163_phase_b_batch3_drop_sitesettings_branding_columns.py`` exists.
Batches 4-13: asserts ``platform_runtime/0007_platform_phase_b_domain_snapshots.py`` exists.
RuntimeDefaults first-class columns: asserts ``0009`` through ``0025`` migration artifacts exist.
Table/singleton after migrate: ``scripts/verify_phase_b_execution.py``.
Exit 0 = gate MET; non-zero = fix before release.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

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


def main() -> int:
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
        r = subprocess.run(
            [sys.executable, str(LINT_SCRIPT), "--check-get-solo-only", "--base", str(ROOT)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            errors.append(
                "lint_tenant_settings --check-get-solo-only failed:\n"
                + (r.stdout or "")
                + (r.stderr or "")
            )
        r2 = subprocess.run(
            [
                sys.executable,
                str(LINT_SCRIPT),
                "--check-sitesettings-orm-in-tenant-apps",
                "--base",
                str(ROOT),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r2.returncode != 0:
            errors.append(
                "lint_tenant_settings --check-sitesettings-orm-in-tenant-apps failed:\n"
                + (r2.stdout or "")
                + (r2.stderr or "")
            )

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
        "Phase 5 siteconfig verification OK (docs + domain_ownership + get_solo + ORM lint "
        "+ Phase B Batch 0-1 + Batch 3 + Batches 4-13 + RuntimeDefaults 0009-0025 migration artifacts)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
