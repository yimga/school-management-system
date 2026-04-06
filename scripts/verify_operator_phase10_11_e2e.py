#!/usr/bin/env python3
"""
Operator Program Phase 10 (ecosystem) + Phase 11 (marketing narrative) — end-to-end slice.

Maps to SOT **3.2.3** (marketplace / packs / migration / interop) + **3.2.4** (marketing front).

Runs (in order):
1. Static marker gate (`verify_program_phase10_phase11_gates.py`)
2. Repo-wide inventory + spine audit (`verify_repo_wide_ecosystem_marketing_audit.py`)
3. **`migrate_gate_test_db.py`** on **``--ux-db-file``** (default
   ``.django_test_dbs/operator_phase1011_e2e.sqlite3``) so pytest and UX use a **dedicated**
   file-backed DB — avoids **SQLite "database is locked"** on shared ``default.sqlite3``.
4. Pytest bundle (same ``DJANGO_TEST_DB_FILE`` as step 3).
5. (unless ``--skip-ux-completion``) ``verify_ux_completion.py`` with
   ``DJANGO_UX_AUDIT_USE_GATE_DB=1`` on that same file (no second migrate).

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).

Fast path without UX audit (still uses dedicated SQLite for pytest)::

    python scripts/verify_operator_phase10_11_e2e.py --skip-ux-completion
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_REPO

DEFAULT_UX_DB_REL = Path(".django_test_dbs") / "operator_phase1011_e2e.sqlite3"


def _run(cmd: list[str], label: str, *, env: dict[str, str] | None = None) -> None:
    print(f"--- {label} ---", flush=True)
    r = subprocess.run(cmd, cwd=ROOT, shell=False, env=env)
    if r.returncode != 0:
        print(f"FAILED: {label}", file=sys.stderr)
        sys.exit(r.returncode)
    print(f"OK: {label}\n", flush=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(DEFAULT_REPO),
        help="Repository root (defaults to this repository root).",
    )
    parser.add_argument(
        "--skip-ux-completion",
        action="store_true",
        help="Skip verify_ux_completion (still migrates dedicated DB + runs pytest).",
    )
    parser.add_argument(
        "--ux-db-file",
        type=Path,
        default=DEFAULT_UX_DB_REL,
        help=(
            "SQLite file for pytest + UX (default: "
            f"{DEFAULT_UX_DB_REL}). "
            "Override if this path is locked (e.g. on Windows)."
        ),
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _configure_root(base: Path) -> None:
    global ROOT
    ROOT = base


def _resolve_ux_db_file(raw_path: Path) -> Path:
    return raw_path if raw_path.is_absolute() else ROOT / raw_path


def _script_path(relative: str) -> str:
    return str(ROOT / relative)


def _pytest_path(relative: str) -> str:
    return str(ROOT / relative)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        _configure_root(_resolve_base(args.base))
    except ValueError as exc:
        print(f"verify_operator_phase10_11_e2e FAILED: {exc}", file=sys.stderr)
        return 1

    py = sys.executable
    ux_path = _resolve_ux_db_file(args.ux_db_file)

    gate_env = os.environ.copy()
    gate_env["DJANGO_TEST_DB_FILE"] = str(ux_path)

    _run(
        [py, _script_path("scripts/verify_program_phase10_phase11_gates.py"), "--base", str(ROOT)],
        "static marker gate",
    )
    _run(
        [py, _script_path("scripts/verify_repo_wide_ecosystem_marketing_audit.py"), "--base", str(ROOT)],
        "repo-wide ecosystem/marketing audit",
    )
    _run(
        [py, _script_path("scripts/migrate_gate_test_db.py")],
        "migrate dedicated E2E SQLite (pytest + UX)",
        env=gate_env,
    )
    _run(
        [
            py,
            "-m",
            "pytest",
            _pytest_path("apps/schools/tests/test_program_phase10_phase11_gates.py"),
            _pytest_path("apps/schools/tests/test_repo_wide_ecosystem_marketing_audit.py"),
            _pytest_path("apps/schools/tests/test_marketing_validation.py"),
            _pytest_path("apps/accounts/tests/test_migration_phase9_detection.py"),
            _pytest_path("apps/accounts/tests/test_district_interop_hub.py"),
            _pytest_path("apps/siteconfig/tests/test_tenant_package_rollback_ui.py"),
            _pytest_path("apps/marketplace/tests/test_marketplace_wedge_coverage.py"),
            _pytest_path("apps/packages/tests/test_engine.py"),
            f"{_pytest_path('apps/accounts/tests/test_smoke_urls.py')}::SmokeUrlResolutionTests::test_tenant_app_catalog_resolves",
            "-q",
        ],
        "pytest Phase 10/11 ecosystem + marketing bundle",
        env=gate_env,
    )

    if args.skip_ux_completion:
        print("verify_operator_phase10_11_e2e: all steps passed (--skip-ux-completion).")
        return 0

    ux_env = gate_env.copy()
    ux_env["DJANGO_UX_AUDIT_USE_GATE_DB"] = "1"
    _run(
        [py, _script_path("scripts/verify_ux_completion.py"), "--base", str(ROOT)],
        "verify_ux_completion.py (DB-backed markers + dashboard/setup contracts)",
        env=ux_env,
    )
    print("verify_operator_phase10_11_e2e: all steps passed (including UX completion audit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
