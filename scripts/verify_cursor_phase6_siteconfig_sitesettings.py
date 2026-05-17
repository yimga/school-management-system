#!/usr/bin/env python3
"""
Cursor Phase 6 — Siteconfig / SiteSettings dismantling — mechanical gate.

Bundles ZIP Phase 5 (includes Phase B migration artifacts) + tenant / Batch3 guardrails
+ ``lint_sitesettings_orm_singleton`` (``SiteSettings.objects`` only in ``models.py`` + ``helpers.py``)
+ ``audit_sitesettings_python_surface.py`` (product-Python surface JSON + same ORM allowlist):

  ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).

E2E migrated DB: pytest apps/platform_runtime/tests/test_phase_b_execution_gate.py (or post-migrate: python scripts/verify_phase_b_execution.py).

This is NOT a substitute for reading docs/phase_audit/PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md;
it enforces **touched** invariants: tenant trees, docs, domain ownership module, Batch3 FK lint.

Exit 0 = all subprocess checks pass.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Cursor Phase 6 siteconfig/sitesettings bundle."
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


def _run(cmd: list[str], label: str, *, root: Path) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        return (
            f"{label} timed out after 180s:\n"
            f"{exc.stdout or ''}\n{exc.stderr or ''}"
        )
    if proc.returncode != 0:
        return f"{label} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return None


def _exact_field_owner_count(domain_ownership: Path) -> int:
    spec = importlib.util.spec_from_file_location(
        "domain_ownership_phase6", domain_ownership
    )
    if spec is None or spec.loader is None:
        return 0
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    d = getattr(mod, "EXACT_FIELD_OWNERS", None)
    if not isinstance(d, dict):
        return 0
    return len(d)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print("verify_cursor_phase6_siteconfig_sitesettings: FAIL", file=sys.stderr)
        print(f"  ---\n{exc}", file=sys.stderr)
        return 1

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    errors: list[str] = []
    audit = root / "docs" / "phase_audit" / "PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md"
    inventory = root / "docs" / "site_settings_usage_inventory.md"
    migration = root / "docs" / "SITECONFIG_OWNERSHIP_MIGRATION.md"
    domain_ownership = root / "apps" / "siteconfig" / "domain_ownership.py"

    for path, label in (
        (audit, "PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md"),
        (inventory, "site_settings_usage_inventory.md"),
        (migration, "SITECONFIG_OWNERSHIP_MIGRATION.md"),
        (domain_ownership, "domain_ownership.py"),
    ):
        if not path.is_file():
            errors.append(f"Missing required file: {_relative(path, root)}")

    if audit.is_file():
        body = audit.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "## 1. SiteSettings physical model",
            "## 4. Mandatory audit (Phase 6 spec checklist)",
            "## 6. Acceptance criteria (Phase 6 mission)",
        ):
            if needle not in body:
                errors.append(f"Audit missing section {needle!r}")

    n_exact = _exact_field_owner_count(domain_ownership)
    if n_exact < 40:
        errors.append(
            f"domain_ownership.EXACT_FIELD_OWNERS too small ({n_exact}); expected >= 40"
        )

    py = sys.executable
    verify_phase_5 = root / "scripts" / "verify_phase_5_siteconfig.py"
    lint_tenant_settings = root / "scripts" / "lint_tenant_settings.py"
    lint_phase_b_batch3 = root / "scripts" / "lint_phase_b_batch3_sitesettings_fk_writes.py"
    lint_singleton = root / "scripts" / "lint_sitesettings_orm_singleton.py"
    audit_surface = root / "scripts" / "audit_sitesettings_python_surface.py"
    typed_map = root / "scripts" / "verify_sitesettings_typed_ownership_map.py"
    cache_rankings_parity = root / "scripts" / "verify_cache_rankings_interval_parity.py"
    checks = [
        ([py, str(verify_phase_5), "--base", str(root)], "verify_phase_5_siteconfig"),
        (
            [py, str(audit_surface)],
            "audit_sitesettings_python_surface (ORM allowlist + JSON)",
        ),
        (
            [
                py,
                str(lint_tenant_settings),
                "--check-get-solo-only",
                "--base",
                str(root),
            ],
            "lint_tenant_settings --check-get-solo-only",
        ),
        (
            [
                py,
                str(lint_tenant_settings),
                "--check-school-settings-features",
                "--base",
                str(root),
            ],
            "lint_tenant_settings --check-school-settings-features",
        ),
        (
            [
                py,
                str(lint_tenant_settings),
                "--check-sitesettings-orm-in-tenant-apps",
                "--base",
                str(root),
            ],
            "lint_tenant_settings --check-sitesettings-orm-in-tenant-apps",
        ),
        (
            [py, str(lint_phase_b_batch3), "--base", str(root)],
            "lint_phase_b_batch3_sitesettings_fk_writes",
        ),
        (
            [py, str(lint_singleton), "--base", str(root)],
            "lint_sitesettings_orm_singleton",
        ),
        (
            [py, str(typed_map)],
            "verify_sitesettings_typed_ownership_map (1042 JSON)",
        ),
        (
            [py, str(cache_rankings_parity)],
            "verify_cache_rankings_interval_parity (1264/1265 slice)",
        ),
        (
            [py, str(root / "scripts" / "verify_top_students_default_limit_parity.py")],
            "verify_top_students_default_limit_parity (1267 slice)",
        ),
    ]
    for cmd, label in checks:
        err = _run(cmd, label, root=root)
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
    raise SystemExit(main(None))
