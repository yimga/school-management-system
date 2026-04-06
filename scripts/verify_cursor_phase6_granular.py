#!/usr/bin/env python3
"""
Cursor Phase 6 - Siteconfig / SiteSettings - granular verification (beyond doc claims).

Runs the standard Phase 6 bundle, Phase 6-specific verifier tests, migration artifact
presence, and inventory/domain ownership invariants.

Exit 0 = all checks pass.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Cursor Phase 6 granular siteconfig/sitesettings proof."
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
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _relative(path: Path, base: Path) -> Path | str:
    try:
        return path.relative_to(base)
    except ValueError:
        return path


def _exact_field_owner_count(domain_ownership: Path) -> int:
    spec = importlib.util.spec_from_file_location(
        "domain_ownership_p6g",
        domain_ownership,
    )
    if spec is None or spec.loader is None:
        return 0
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    d = getattr(mod, "EXACT_FIELD_OWNERS", None)
    return len(d) if isinstance(d, dict) else 0


def _run_pytest(
    paths: list[str], label: str, *, root: Path, timeout: int = 480
) -> str | None:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *paths, "-q", "--no-header"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return (
            f"{label} timed out after {timeout}s:\n"
            f"{exc.stdout or ''}\n{exc.stderr or ''}"
        )
    if proc.returncode != 0:
        return f"{label} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return None


def _run_cmd(
    cmd: list[str], label: str, *, root: Path, timeout: int
) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return (
            f"{label} timed out after {timeout}s:\n"
            f"{exc.stdout or ''}\n{exc.stderr or ''}"
        )
    if proc.returncode != 0:
        return f"{label} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print("verify_cursor_phase6_granular: FAIL", file=sys.stderr)
        print(f"  ---\n{exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    phase6_audit = root / "docs" / "phase_audit" / "PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md"
    inventory = root / "docs" / "site_settings_usage_inventory.md"
    domain_ownership = root / "apps" / "siteconfig" / "domain_ownership.py"
    mig_0162 = (
        root / "apps" / "siteconfig" / "migrations" / "0162_phase_b_slim_sitesettings.py"
    )
    mig_0163 = (
        root
        / "apps"
        / "siteconfig"
        / "migrations"
        / "0163_phase_b_batch3_drop_sitesettings_branding_columns.py"
    )
    bundle = root / "scripts" / "verify_cursor_phase6_siteconfig_sitesettings.py"

    if not bundle.is_file():
        errors.append(f"Missing {_relative(bundle, root)}")
    elif err := _run_cmd(
        [sys.executable, str(bundle), "--base", str(root)],
        "verify_cursor_phase6_siteconfig_sitesettings",
        root=root,
        timeout=240,
    ):
        errors.append(err)

    for path, label, needles in (
        (
            phase6_audit,
            "PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md",
            (
                "## 1. SiteSettings physical model",
                "## 8. Phase B repository closure",
                "get_effective_site_settings",
            ),
        ),
        (
            inventory,
            "site_settings_usage_inventory.md",
            ("**Status:** **DONE**", "get_effective_site_settings"),
        ),
    ):
        if not path.is_file():
            errors.append(f"Missing {_relative(path, root)}")
        else:
            body = path.read_text(encoding="utf-8", errors="replace")
            for needle in needles:
                if needle not in body:
                    errors.append(f"{label} missing required anchor {needle!r}")

    n_exact = _exact_field_owner_count(domain_ownership)
    if n_exact < 40:
        errors.append(
            f"domain_ownership.EXACT_FIELD_OWNERS too small ({n_exact}); expected >= 40"
        )

    for mig, label in (
        (mig_0162, "0162 slim SiteSettings"),
        (mig_0163, "0163 drop branding FKs"),
    ):
        if not mig.is_file():
            errors.append(f"Missing migration ({label}): {_relative(mig, root)}")

    if err := _run_pytest(
        [
            "apps/platform_runtime/tests/test_tenant_settings_lint.py::TenantSettingsLintTests::test_verify_phase1_settings_gravity_passes",
            "apps/platform_runtime/tests/test_tenant_settings_lint.py::TenantSettingsLintTests::test_verify_siteconfig_decomposition_depth_passes",
            "apps/platform_runtime/tests/test_tenant_settings_lint.py::TenantSettingsLintTests::test_verify_phase_b_snapshot_migration_alignment_passes",
            "apps/platform_runtime/tests/test_tenant_settings_lint.py::TenantSettingsLintTests::test_verify_phase_b_execution_passes",
            "apps/platform_runtime/tests/test_tenant_settings_lint.py::TenantSettingsLintTests::test_verify_marketplace_integration_first_class_parity_passes",
            "apps/platform_runtime/tests/test_tenant_settings_lint.py::TenantSettingsLintTests::test_verify_domain_ownership_exact_storage_passes",
        ],
        "Phase 6 targeted verifier suite",
        root=root,
        timeout=900,
    ):
        errors.append(err)

    if errors:
        print("verify_cursor_phase6_granular: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  ---\n{err}", file=sys.stderr)
        return 1

    print(
        "verify_cursor_phase6_granular: PASS",
        f"(bundle + inventory/audit anchors + EXACT_FIELD_OWNERS={n_exact} + pytest gates)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
