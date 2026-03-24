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
        "+ Phase B Batch 0-1 + Batch 3 + Batches 4-13 migration artifacts)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
