#!/usr/bin/env python3
"""
Cursor Phase 6 — Siteconfig / SiteSettings dismantling — mechanical gate.

Bundles ZIP Phase 5 (includes Phase B migration artifacts) + tenant / Batch3 guardrails
+ ``lint_sitesettings_orm_singleton`` (``SiteSettings.objects`` only in ``models.py`` + ``helpers.py``):

  python scripts/verify_cursor_phase6_siteconfig_sitesettings.py

E2E migrated DB: pytest apps/platform_runtime/tests/test_phase_b_execution_gate.py (or post-migrate: python scripts/verify_phase_b_execution.py).

This is NOT a substitute for reading docs/phase_audit/PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md;
it enforces **touched** invariants: tenant trees, docs, domain ownership module, Batch3 FK lint.

Exit 0 = all subprocess checks pass.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIT = ROOT / "docs" / "phase_audit" / "PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md"
INVENTORY = ROOT / "docs" / "site_settings_usage_inventory.md"
MIGRATION = ROOT / "docs" / "SITECONFIG_OWNERSHIP_MIGRATION.md"
DOMAIN_OWNERSHIP = ROOT / "apps" / "siteconfig" / "domain_ownership.py"


def _run(cmd: list[str], label: str) -> str | None:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        return f"{label} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return None


def _exact_field_owner_count() -> int:
    spec = importlib.util.spec_from_file_location(
        "domain_ownership_phase6", DOMAIN_OWNERSHIP
    )
    if spec is None or spec.loader is None:
        return 0
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    d = getattr(mod, "EXACT_FIELD_OWNERS", None)
    if not isinstance(d, dict):
        return 0
    return len(d)


def main() -> int:
    errors: list[str] = []

    for path, label in (
        (AUDIT, "PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md"),
        (INVENTORY, "site_settings_usage_inventory.md"),
        (MIGRATION, "SITECONFIG_OWNERSHIP_MIGRATION.md"),
        (DOMAIN_OWNERSHIP, "domain_ownership.py"),
    ):
        if not path.is_file():
            errors.append(f"Missing required file: {path.relative_to(ROOT)}")

    if AUDIT.is_file():
        body = AUDIT.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "## 1. SiteSettings physical model",
            "## 4. Mandatory audit (Phase 6 spec checklist)",
            "## 6. Acceptance criteria (Phase 6 mission)",
        ):
            if needle not in body:
                errors.append(f"Audit missing section {needle!r}")

    n_exact = _exact_field_owner_count()
    if n_exact < 40:
        errors.append(
            f"domain_ownership.EXACT_FIELD_OWNERS too small ({n_exact}); expected >= 40"
        )

    py = sys.executable
    checks = [
        ([py, str(ROOT / "scripts" / "verify_phase_5_siteconfig.py")], "verify_phase_5_siteconfig"),
        (
            [
                py,
                str(ROOT / "scripts" / "lint_tenant_settings.py"),
                "--check-get-solo-only",
                "--base",
                str(ROOT),
            ],
            "lint_tenant_settings --check-get-solo-only",
        ),
        (
            [
                py,
                str(ROOT / "scripts" / "lint_tenant_settings.py"),
                "--check-school-settings-features",
                "--base",
                str(ROOT),
            ],
            "lint_tenant_settings --check-school-settings-features",
        ),
        (
            [
                py,
                str(ROOT / "scripts" / "lint_tenant_settings.py"),
                "--check-sitesettings-orm-in-tenant-apps",
                "--base",
                str(ROOT),
            ],
            "lint_tenant_settings --check-sitesettings-orm-in-tenant-apps",
        ),
        (
            [py, str(ROOT / "scripts" / "lint_phase_b_batch3_sitesettings_fk_writes.py")],
            "lint_phase_b_batch3_sitesettings_fk_writes",
        ),
        (
            [py, str(ROOT / "scripts" / "lint_sitesettings_orm_singleton.py"), "--base", str(ROOT)],
            "lint_sitesettings_orm_singleton",
        ),
    ]
    for cmd, label in checks:
        err = _run(cmd, label)
        if err:
            errors.append(err)

    if errors:
        print("verify_cursor_phase6_siteconfig_sitesettings: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  ---\n{e}", file=sys.stderr)
        return 1

    print(
        "verify_cursor_phase6_siteconfig_sitesettings: PASS",
        f"(EXACT_FIELD_OWNERS={n_exact} keys; ZIP Phase 5 + tenant lints + Batch3 FK + "
        f"singleton ORM lint; E2E DB: test_phase_b_execution_gate.py; deploy: verify_phase_b_execution.py)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
