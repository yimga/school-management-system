#!/usr/bin/env python3
"""Phase 6 turbo verifier: runtime + tests gate for zero_form_bootstrap."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_PATH = REPO / "docs" / "generated" / "zero_form_bootstrap_audit.json"

CONTRACT_MODULE = "apps.governance.turbo.zero_form_bootstrap"
TEST_MODULE = "apps.governance.turbo.tests.test_zero_form_bootstrap"


def _run_runtime_health() -> tuple[bool, dict | None, str | None]:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    try:
        module = importlib.import_module(CONTRACT_MODULE)
    except ImportError as exc:
        return False, None, f"contract_module_unimportable:{exc}"
    if not hasattr(module, "runtime_health"):
        return False, None, "missing_runtime_health_callable"
    try:
        health = module.runtime_health()
    except Exception as exc:
        return False, None, f"runtime_health_raised:{exc!r}"
    if not isinstance(health, dict):
        return False, None, "runtime_health_returned_non_dict"
    return bool(health.get("healthy")), health, None


def _run_tests() -> tuple[bool, int, int]:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    loader = unittest.TestLoader()
    try:
        suite = loader.loadTestsFromName(TEST_MODULE)
    except (ImportError, AttributeError):
        return False, 0, 1
    runner = unittest.TextTestRunner(verbosity=0, stream=open(REPO / "logs" / "phase6_turbo_verifier_run.log", "a", encoding="utf-8") if (REPO / "logs").is_dir() else None)
    result = runner.run(suite)
    return result.wasSuccessful(), result.testsRun, len(result.failures) + len(result.errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    healthy, health, health_reason = _run_runtime_health()
    if not healthy:
        failures.append(f"runtime_health_not_healthy:{health_reason or (health or {}).get('reason') or 'unknown'}")

    tests_ok, tests_run, tests_failed = _run_tests()
    if not tests_ok:
        failures.append(f"tests_failed:run={tests_run}_failed={tests_failed}")

    verdict_slug = "ZERO_FORM_BOOTSTRAP"
    verdict = f"{verdict_slug}_PASS" if not failures else f"{verdict_slug}_FAIL"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "finding_count": len(failures),
        "runtime_health": health,
        "tests_run": tests_run,
        "tests_failed": tests_failed,
        "failures": failures,
    }
    if args.json:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if failures:
        print(f"verify_zero_form_bootstrap: {verdict} ({len(failures)})", file=sys.stderr)
        for line in failures[:10]:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"verify_zero_form_bootstrap: {verdict} (runtime healthy, {tests_run} tests passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
