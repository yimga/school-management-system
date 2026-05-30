#!/usr/bin/env python3
"""Upgrade each Phase 6 turbo verifier to gate on real runtime health, not just scaffold-presence.

The upgraded verifier:
  1. Imports the contract module.
  2. Calls runtime_health() and demands healthy == True.
  3. Runs the companion test module via unittest discovery; demands zero failures.
  4. Writes a structured audit JSON.

If runtime_health() reports unhealthy or any test fails, the verifier exits 1.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER = logging.getLogger("upgrade_phase6_verifiers")

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


VERIFIER_TO_MODULE: dict[str, tuple[str, str]] = {
    "verify_matrix_freshness.py": ("agentic_self_healing_matrix", "test_agentic_self_healing_matrix"),
    "verify_tla_specs.py": ("formal_verification_tla", "test_formal_verification_tla"),
    "verify_compliance_engine.py": ("realtime_compliance_engine", "test_realtime_compliance_engine"),
    "verify_sovereignty_trust_score.py": ("sovereignty_trust_score", "test_sovereignty_trust_score"),
    "verify_cross_vertical_kernel.py": ("cross_vertical_kernel", "test_cross_vertical_kernel"),
    "verify_multimodal_terminology.py": ("multimodal_terminology", "test_multimodal_terminology"),
    "verify_regulator_api_federation.py": ("regulator_api_federation", "test_regulator_api_federation"),
    "verify_adversarial_redteam.py": ("adversarial_redteam", "test_adversarial_redteam"),
    "verify_w3c_verifiable_credentials.py": ("w3c_verifiable_credentials", "test_w3c_verifiable_credentials"),
    "verify_time_traveling_matrix.py": ("time_traveling_matrix", "test_time_traveling_matrix"),
    "verify_zero_form_bootstrap.py": ("zero_form_bootstrap", "test_zero_form_bootstrap"),
    "verify_ai_policy_copilot.py": ("ai_policy_copilot", "test_ai_policy_copilot"),
    "verify_cross_org_marketplace.py": ("cross_org_marketplace", "test_cross_org_marketplace"),
    "verify_federated_emis_aggregator.py": ("federated_emis_aggregator", "test_federated_emis_aggregator"),
    "verify_competitor_tracker.py": ("living_competitor_tracker", "test_living_competitor_tracker"),
}


VERIFIER_TEMPLATE = '''#!/usr/bin/env python3
"""Phase 6 turbo verifier: runtime + tests gate for {contract_slug}."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_PATH = REPO / "docs" / "generated" / "{audit_slug}.json"

CONTRACT_MODULE = "apps.governance.turbo.{contract_slug}"
TEST_MODULE = "apps.governance.turbo.tests.{test_module_slug}"


def _run_runtime_health() -> tuple[bool, dict | None, str | None]:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    try:
        module = importlib.import_module(CONTRACT_MODULE)
    except ImportError as exc:
        return False, None, f"contract_module_unimportable:{{exc}}"
    if not hasattr(module, "runtime_health"):
        return False, None, "missing_runtime_health_callable"
    try:
        health = module.runtime_health()
    except Exception as exc:
        return False, None, f"runtime_health_raised:{{exc!r}}"
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
        failures.append(f"runtime_health_not_healthy:{{health_reason or (health or {{}}).get('reason') or 'unknown'}}")

    tests_ok, tests_run, tests_failed = _run_tests()
    if not tests_ok:
        failures.append(f"tests_failed:run={{tests_run}}_failed={{tests_failed}}")

    verdict_slug = "{verdict_slug}"
    verdict = f"{{verdict_slug}}_PASS" if not failures else f"{{verdict_slug}}_FAIL"
    payload = {{
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "finding_count": len(failures),
        "runtime_health": health,
        "tests_run": tests_run,
        "tests_failed": tests_failed,
        "failures": failures,
    }}
    if args.json:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
    if failures:
        print(f"{verifier_name}: {{verdict}} ({{len(failures)}})", file=sys.stderr)
        for line in failures[:10]:
            print(f"  - {{line}}", file=sys.stderr)
        return 1
    print(f"{verifier_name}: {{verdict}} (runtime healthy, {{tests_run}} tests passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _slugify_verdict(name: str) -> str:
    stem = name.removeprefix("verify_").removesuffix(".py")
    return stem.upper()


def _slugify_audit(name: str) -> str:
    stem = name.removeprefix("verify_").removesuffix(".py")
    return f"{stem}_audit"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    written = 0
    for verifier_name, (contract_slug, test_module_slug) in VERIFIER_TO_MODULE.items():
        path = SCRIPTS / verifier_name
        text = VERIFIER_TEMPLATE.format(
            verifier_name=verifier_name.removesuffix(".py"),
            contract_slug=contract_slug,
            test_module_slug=test_module_slug,
            audit_slug=_slugify_audit(verifier_name),
            verdict_slug=_slugify_verdict(verifier_name),
        )
        path.write_text(text, encoding="utf-8")
        written += 1
    LOGGER.info("verifiers upgraded: %d", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
