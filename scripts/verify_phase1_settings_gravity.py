#!/usr/bin/env python3
"""
Phase 1 gate: SiteSettings/siteconfig gravity dismantle checks for touched flows.

This script is intentionally mechanical and CI-friendly:
- verifies ownership classification coverage in apps/siteconfig/domain_ownership.py
- verifies migration map docs exist
- enforces tenant-path guardrails via lint_tenant_settings.py
- audits get_solo() allowlist drift (must stay at zero)
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOMAIN_OWNERSHIP = ROOT / "apps" / "siteconfig" / "domain_ownership.py"
USAGE_INVENTORY = ROOT / "docs" / "site_settings_usage_inventory.md"
MIGRATION_MAP = ROOT / "docs" / "SITECONFIG_OWNERSHIP_MIGRATION.md"

REQUIRED_OWNER_KEYS = {
    "safe_platform_default",
    "brand_experience",
    "runtime_blueprints",
    "policies_rules",
    "plans_entitlements",
    "global_registries",
    "marketplace_integrations",
    "delete",
}


def _run(cmd: list[str], label: str, timeout: int = 180) -> str | None:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        return f"{label} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return None


def _load_owner_sets() -> tuple[set[str], set[str]]:
    spec = importlib.util.spec_from_file_location("domain_ownership_phase1", DOMAIN_OWNERSHIP)
    if spec is None or spec.loader is None:
        return set(), set()
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    exact = getattr(module, "EXACT_FIELD_OWNERS", {}) or {}
    prefix = getattr(module, "PREFIX_FIELD_OWNERS", ()) or ()

    exact_values = set(exact.values()) if isinstance(exact, dict) else set()
    prefix_values: set[str] = set()
    if isinstance(prefix, tuple):
        for item in prefix:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], str):
                prefix_values.add(item[1])
    return exact_values, prefix_values


def _parse_allowlisted_get_solo_total(stdout: str) -> int | None:
    match = re.search(r"Total allowlisted:\s*(\d+)", stdout)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    for path in (DOMAIN_OWNERSHIP, USAGE_INVENTORY, MIGRATION_MAP):
        if not path.is_file():
            errors.append(f"Missing required artifact: {path.relative_to(ROOT)}")

    exact_owners, prefix_owners = _load_owner_sets()
    all_owners = exact_owners | prefix_owners
    missing = sorted(REQUIRED_OWNER_KEYS - all_owners)
    if missing:
        errors.append(
            "domain_ownership owner coverage incomplete. Missing keys: "
            + ", ".join(missing)
        )
    ownership_source = DOMAIN_OWNERSHIP.read_text(encoding="utf-8", errors="replace")
    if '"metadata_governance"' not in ownership_source:
        errors.append('domain_ownership fallback owner "metadata_governance" missing.')

    py = sys.executable
    checks = [
        (
            [py, str(ROOT / "scripts" / "lint_tenant_settings.py"), "--check-get-solo-only", "--base", str(ROOT)],
            "lint_tenant_settings --check-get-solo-only",
        ),
        (
            [py, str(ROOT / "scripts" / "lint_tenant_settings.py"), "--check-school-settings-features", "--base", str(ROOT)],
            "lint_tenant_settings --check-school-settings-features",
        ),
        (
            [py, str(ROOT / "scripts" / "lint_tenant_settings.py"), "--check-sitesettings-orm-in-tenant-apps", "--base", str(ROOT)],
            "lint_tenant_settings --check-sitesettings-orm-in-tenant-apps",
        ),
    ]
    for cmd, label in checks:
        err = _run(cmd, label, timeout=180)
        if err:
            errors.append(err)

    allowlisted = subprocess.run(
        [
            py,
            str(ROOT / "scripts" / "lint_tenant_settings.py"),
            "--report-allowlisted",
            "--base",
            str(ROOT),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if allowlisted.returncode != 0:
        errors.append(
            "lint_tenant_settings --report-allowlisted failed "
            f"(exit {allowlisted.returncode}):\n{allowlisted.stdout}\n{allowlisted.stderr}"
        )
    else:
        count = _parse_allowlisted_get_solo_total(allowlisted.stdout or "")
        if count is None:
            warnings.append("Could not parse allowlisted get_solo total from lint output.")
        elif count > 0:
            errors.append(
                f"Allowlisted get_solo() drift detected (expected 0, found {count})."
            )

    if errors:
        print("verify_phase1_settings_gravity: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  ---\n{item}", file=sys.stderr)
        if warnings:
            print("Warnings:", file=sys.stderr)
            for item in warnings:
                print(f"  - {item}", file=sys.stderr)
        return 1

    status = "verify_phase1_settings_gravity: PASS (owner coverage + tenant guardrails + get_solo allowlist)"
    if warnings:
        status += " with warnings: " + "; ".join(warnings)
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
