#!/usr/bin/env python3
"""
Phase 1 gate: SiteSettings/siteconfig gravity dismantle checks for touched flows.

This script is intentionally mechanical and CI-friendly:
- verifies ownership classification coverage in apps/siteconfig/domain_ownership.py
- verifies migration map docs exist
- enforces tenant-path guardrails via lint_tenant_settings.py
- audits get_solo() allowlist drift (must stay at zero)

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Phase 1 settings gravity."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _relative(path: Path, base: Path) -> Path | str:
    try:
        return path.relative_to(base)
    except ValueError:
        return path


def _run(
    cmd: list[str], label: str, *, root: Path, timeout: int = 180
) -> str | None:
    proc = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        return f"{label} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return None


def _load_owner_sets(domain_ownership: Path) -> tuple[set[str], set[str]]:
    spec = importlib.util.spec_from_file_location(
        "domain_ownership_phase1",
        domain_ownership,
    )
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print("verify_phase1_settings_gravity: FAIL", file=sys.stderr)
        print(f"  ---\n{exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    domain_ownership = root / "apps" / "siteconfig" / "domain_ownership.py"
    usage_inventory = root / "docs" / "site_settings_usage_inventory.md"
    migration_map = root / "docs" / "SITECONFIG_OWNERSHIP_MIGRATION.md"

    for path in (domain_ownership, usage_inventory, migration_map):
        if not path.is_file():
            errors.append(f"Missing required artifact: {_relative(path, root)}")

    exact_owners, prefix_owners = _load_owner_sets(domain_ownership)
    all_owners = exact_owners | prefix_owners
    missing = sorted(REQUIRED_OWNER_KEYS - all_owners)
    if missing:
        errors.append(
            "domain_ownership owner coverage incomplete. Missing keys: "
            + ", ".join(missing)
        )
    if domain_ownership.is_file():
        ownership_source = domain_ownership.read_text(
            encoding="utf-8", errors="replace"
        )
        if '"metadata_governance"' not in ownership_source:
            errors.append('domain_ownership fallback owner "metadata_governance" missing.')

    py = sys.executable
    lint_script = root / "scripts" / "lint_tenant_settings.py"
    checks = [
        (
            [py, str(lint_script), "--check-get-solo-only", "--base", str(root)],
            "lint_tenant_settings --check-get-solo-only",
        ),
        (
            [py, str(lint_script), "--check-school-settings-features", "--base", str(root)],
            "lint_tenant_settings --check-school-settings-features",
        ),
        (
            [
                py,
                str(lint_script),
                "--check-sitesettings-orm-in-tenant-apps",
                "--base",
                str(root),
            ],
            "lint_tenant_settings --check-sitesettings-orm-in-tenant-apps",
        ),
    ]
    for cmd, label in checks:
        err = _run(cmd, label, root=root, timeout=180)
        if err:
            errors.append(err)

    allowlisted = subprocess.run(
        [
            py,
            str(lint_script),
            "--report-allowlisted",
            "--base",
            str(root),
        ],
        cwd=str(root),
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
    raise SystemExit(main(None))
