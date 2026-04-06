#!/usr/bin/env python3
"""
§7 Ecosystem and pack seeding — executable verification.

RUNMYCAMPUS SOT §7 "How to verify §7": runs the same checks that the doc specifies.
Exit 0 only if all steps pass. Use in CI or locally to confirm §7 gate.

Steps:
  1. generate_platform_inventory.py --check (committed inventory matches current state)
  2. test_marketplace_catalog_minimums (catalog counts meet MARKETPLACE_MINIMUMS)
  3. MARKETPLACE_MINIMUMS keys present in catalog_counts (sanity)

Fresh test DB (recommended on Windows / half-migrated SQLite):
  PRE_GATE_FRESH_TEST_DB=1  — remove ``.django_test_dbs/pre_deploy_gate.sqlite3`` before step 2 (best-effort).
  If step 2 fails with WinError 32 (file in use), set e.g.
  ``DJANGO_TEST_DB_FILE=.django_test_dbs/section7_verify.sqlite3`` so the test uses a dedicated file.

Speed vs reliability for step 2:
  VERIFY_SECTION7_KEEPDB=1  — pass ``--keepdb`` to ``manage.py test`` (faster; fails if DB is corrupt/locked).
  Default: no ``--keepdb`` so Django rebuilds the test DB (slower, reliable).

Windows (WinError 32):
  When not using ``--keepdb``, Django may try to delete/replace a **shared** test DB file that is
  still locked. This script then sets ``DJANGO_TEST_DB_FILE`` to a **unique**
  ``.django_test_dbs/section7_verify_<uuid>.sqlite3`` per run unless
  ``SECTION7_FIXED_TEST_DB=1`` (uses ``section7_verify.sqlite3``) or you preset ``DJANGO_TEST_DB_FILE``.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT


def _default_gate_db(root: Path) -> Path:
    return root / ".django_test_dbs" / "pre_deploy_gate.sqlite3"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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


def _configure_root(base: Path) -> None:
    global ROOT
    ROOT = base
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _configure_django_test_db_for_step2(root: Path) -> None:
    """
    Set DJANGO_TEST_DB_FILE before subprocess so manage.py test uses a predictable path.

    - VERIFY_SECTION7_KEEPDB=1: reuse ``pre_deploy_gate.sqlite3`` (or existing env) — fast.
    - Else: unique ``section7_verify_<uuid>.sqlite3`` so Windows does not hit WinError 32
      when Django drops/recreates the test database file.
    """
    use_keepdb = (os.environ.get("VERIFY_SECTION7_KEEPDB") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if use_keepdb:
        if not os.environ.get("DJANGO_TEST_DB_FILE"):
            os.environ["DJANGO_TEST_DB_FILE"] = str(_default_gate_db(root))
        return
    if (os.environ.get("SECTION7_FIXED_TEST_DB") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        if not os.environ.get("DJANGO_TEST_DB_FILE"):
            os.environ["DJANGO_TEST_DB_FILE"] = str(
                root / ".django_test_dbs" / "section7_verify.sqlite3"
            )
        return
    if os.environ.get("DJANGO_TEST_DB_FILE"):
        # User explicitly set path (e.g. CI); do not override.
        return
    dbs = root / ".django_test_dbs"
    dbs.mkdir(parents=True, exist_ok=True)
    os.environ["DJANGO_TEST_DB_FILE"] = str(
        dbs / f"section7_verify_{uuid.uuid4().hex}.sqlite3"
    )


def _maybe_remove_gate_test_db_for_fresh_run(root: Path) -> None:
    """Match pre_deploy_gate: PRE_GATE_FRESH_TEST_DB=1 nukes the file-backed gate DB."""
    raw = (os.environ.get("PRE_GATE_FRESH_TEST_DB") or "").strip().lower()
    if raw not in ("1", "true", "yes"):
        return
    db_path = Path(os.environ.get("DJANGO_TEST_DB_FILE", str(_default_gate_db(root))))
    if not db_path.is_absolute():
        db_path = root / db_path
    try:
        db_path.unlink(missing_ok=True)
    except OSError:
        pass


def run(
    cmd: list[str], label: str, *, timeout: int = 120, root: Path | None = None
) -> tuple[bool, str]:
    """Run command; return (success, message)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=root or ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, "PASS"
        return (
            False,
            result.stderr.strip()
            or result.stdout.strip()
            or f"exit {result.returncode}",
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except FileNotFoundError:
        return False, "command not found"
    except Exception as e:
        return False, str(e)


def check_minimums_keys(root: Path) -> tuple[bool, str]:
    """Verify MARKETPLACE_MINIMUMS has the keys required by §7."""
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from apps.platform_runtime.catalog_counts import MARKETPLACE_MINIMUMS

        required = {
            "first_party_apps",
            "blueprint_packs",
            "workflow_packs",
            "dashboard_packs",
            "policy_bundles",
        }
        missing = required - set(MARKETPLACE_MINIMUMS.keys())
        if missing:
            return False, f"MARKETPLACE_MINIMUMS missing keys: {missing}"
        return True, "PASS"
    except Exception as e:
        return False, str(e)


def main(argv: list[str] | None = None) -> int:
    try:
        _configure_root(_resolve_base(parse_args(argv).base))
    except ValueError as exc:
        print(f"verify_section7_gate: {exc}", file=sys.stderr)
        return 1

    failures: list[str] = []
    n = 0

    _configure_django_test_db_for_step2(ROOT)
    _maybe_remove_gate_test_db_for_fresh_run(ROOT)

    # Step 1: platform inventory --check
    n += 1
    ok, msg = run(
        [sys.executable, "scripts/generate_platform_inventory.py", "--check"],
        "§7 step 1: generate_platform_inventory --check",
        root=ROOT,
    )
    if ok:
        print(f"  [{n}] generate_platform_inventory --check: PASS")
    else:
        print(
            f"  [{n}] generate_platform_inventory --check: FAIL — {msg}",
            file=sys.stderr,
        )
        failures.append(f"Step 1: {msg}")

    # Step 2: catalog minimums test (requires Django + DB)
    n += 1
    test_cmd = [
        sys.executable,
        "manage.py",
        "test",
        "apps.platform_runtime.tests.test_marketplace_catalog_minimums",
        "--noinput",
        "-v",
        "0",
    ]
    # Default: no --keepdb — rebuilds test DB so half-migrated/corrupt SQLite cannot fail §7.
    # VERIFY_SECTION7_KEEPDB=1 for faster reruns when the gate DB is known good.
    if (os.environ.get("VERIFY_SECTION7_KEEPDB") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        test_cmd.append("--keepdb")
    ok, msg = run(
        test_cmd,
        "§7 step 2: test_marketplace_catalog_minimums",
        timeout=900,
        root=ROOT,
    )
    if ok:
        print(f"  [{n}] test_marketplace_catalog_minimums: PASS")
    else:
        print(
            f"  [{n}] test_marketplace_catalog_minimums: FAIL — {msg[:200]}",
            file=sys.stderr,
        )
        failures.append(f"Step 2: {msg[:200]}")

    # Step 3: MARKETPLACE_MINIMUMS keys
    n += 1
    ok, msg = check_minimums_keys(ROOT)
    if ok:
        print(f"  [{n}] MARKETPLACE_MINIMUMS keys: PASS")
    else:
        print(f"  [{n}] MARKETPLACE_MINIMUMS keys: FAIL — {msg}", file=sys.stderr)
        failures.append(f"Step 3: {msg}")

    if failures:
        print("\n§7 verification: FAIL", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\n§7 verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
