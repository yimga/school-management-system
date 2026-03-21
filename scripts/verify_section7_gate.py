#!/usr/bin/env python3
"""
§7 Ecosystem and pack seeding — executable verification.

RUNMYCAMPUS SOT §7 "How to verify §7": runs the same checks that the doc specifies.
Exit 0 only if all steps pass. Use in CI or locally to confirm §7 gate.

Steps:
  1. generate_platform_inventory.py --check (committed inventory matches current state)
  2. test_marketplace_catalog_minimums (catalog counts meet MARKETPLACE_MINIMUMS)
  3. MARKETPLACE_MINIMUMS keys present in catalog_counts (sanity)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Align with scripts/pre_deploy_gate.sh: use the same dedicated SQLite test DB so
# `manage.py test` in step 2 does not hit a locked/default DB or wrong engine on Windows/CI.
_DEFAULT_GATE_DB = ROOT / ".django_test_dbs" / "pre_deploy_gate.sqlite3"
if not os.environ.get("DJANGO_TEST_DB_FILE"):
    os.environ["DJANGO_TEST_DB_FILE"] = str(_DEFAULT_GATE_DB)


def run(
    cmd: list[str], label: str, *, timeout: int = 120
) -> tuple[bool, str]:
    """Run command; return (success, message)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=ROOT,
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


def check_minimums_keys() -> tuple[bool, str]:
    """Verify MARKETPLACE_MINIMUMS has the keys required by §7."""
    try:
        sys.path.insert(0, str(ROOT))
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


def main() -> int:
    failures: list[str] = []
    n = 0

    # Step 1: platform inventory --check
    n += 1
    ok, msg = run(
        [sys.executable, "scripts/generate_platform_inventory.py", "--check"],
        "§7 step 1: generate_platform_inventory --check",
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
    ok, msg = run(
        [
            sys.executable,
            "manage.py",
            "test",
            "apps.platform_runtime.tests.test_marketplace_catalog_minimums",
            "--noinput",
            "-v",
            "0",
            # Avoid WinError 32 when another process holds the test DB file.
            "--keepdb",
        ],
        "§7 step 2: test_marketplace_catalog_minimums",
        timeout=300,
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
    ok, msg = check_minimums_keys()
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
    sys.exit(main())
