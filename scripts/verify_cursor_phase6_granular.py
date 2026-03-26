#!/usr/bin/env python3
"""
Cursor Phase 6 — Siteconfig / SiteSettings — granular verification (beyond doc claims).

Runs the standard Phase 6 bundle, E2E Phase B DB tests, migration artifact presence,
inventory/domain ownership invariants, and optional domain snapshot tests.

Exit 0 = all checks pass.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PHASE6_AUDIT = ROOT / "docs" / "phase_audit" / "PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md"
INVENTORY = ROOT / "docs" / "site_settings_usage_inventory.md"
DOMAIN_OWNERSHIP = ROOT / "apps" / "siteconfig" / "domain_ownership.py"
MIG_0162 = ROOT / "apps" / "siteconfig" / "migrations" / "0162_phase_b_slim_sitesettings.py"
MIG_0163 = (
    ROOT
    / "apps"
    / "siteconfig"
    / "migrations"
    / "0163_phase_b_batch3_drop_sitesettings_branding_columns.py"
)
BUNDLE = ROOT / "scripts" / "verify_cursor_phase6_siteconfig_sitesettings.py"


def _exact_field_owner_count() -> int:
    spec = importlib.util.spec_from_file_location(
        "domain_ownership_p6g", DOMAIN_OWNERSHIP
    )
    if spec is None or spec.loader is None:
        return 0
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    d = getattr(mod, "EXACT_FIELD_OWNERS", None)
    return len(d) if isinstance(d, dict) else 0


def _run_pytest(paths: list[str], label: str) -> str | None:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q", "--no-header"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=240,
    )
    if proc.returncode != 0:
        return f"{label} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return None


def main() -> int:
    errors: list[str] = []

    if not BUNDLE.is_file():
        errors.append(f"Missing {BUNDLE.relative_to(ROOT)}")
    else:
        proc = subprocess.run(
            [sys.executable, str(BUNDLE)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=240,
        )
        if proc.returncode != 0:
            errors.append(
                f"verify_cursor_phase6_siteconfig_sitesettings failed:\n{proc.stdout}\n{proc.stderr}"
            )

    for path, label, needles in (
        (
            PHASE6_AUDIT,
            "PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md",
            (
                "## 1. SiteSettings physical model",
                "## 8. Phase B repository closure",
                "get_effective_site_settings",
            ),
        ),
        (
            INVENTORY,
            "site_settings_usage_inventory.md",
            ("**Status:** **DONE**", "get_effective_site_settings"),
        ),
    ):
        if not path.is_file():
            errors.append(f"Missing {path.relative_to(ROOT)}")
        else:
            body = path.read_text(encoding="utf-8", errors="replace")
            for n in needles:
                if n not in body:
                    errors.append(f"{label} missing required anchor {n!r}")

    n_exact = _exact_field_owner_count()
    if n_exact < 40:
        errors.append(
            f"domain_ownership.EXACT_FIELD_OWNERS too small ({n_exact}); expected >= 40"
        )

    for mig, label in (
        (MIG_0162, "0162 slim SiteSettings"),
        (MIG_0163, "0163 drop branding FKs"),
    ):
        if not mig.is_file():
            errors.append(f"Missing migration ({label}): {mig.relative_to(ROOT)}")

    if err := _run_pytest(
        [
            "apps/platform_runtime/tests/test_tenant_settings_lint.py",
            "apps/platform_runtime/tests/test_phase_b_execution_gate.py",
        ],
        "Phase 6 tenant lint + Phase B E2E gate",
    ):
        errors.append(err)

    if err := _run_pytest(
        ["apps/platform_runtime/tests/test_phase_b_domain_snapshots.py"],
        "Phase B domain snapshots (save → rows)",
    ):
        errors.append(err)

    if errors:
        print("verify_cursor_phase6_granular: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  ---\n{e}", file=sys.stderr)
        return 1

    print(
        "verify_cursor_phase6_granular: PASS",
        f"(bundle + inventory/audit anchors + EXACT_FIELD_OWNERS={n_exact} + pytest gates)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
