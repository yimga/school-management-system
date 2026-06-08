#!/usr/bin/env python3
"""Phase P7 gate for fail-closed intelligence-feature promotion."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "var" / "evidence" / "promotion" / "repository_readiness.json"


def main() -> int:
    errors: list[str] = []
    catalog_path = ROOT / "config" / "intelligence_feature_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    dimensions = catalog.get("evidence_dimensions") or []
    features = catalog.get("features") or []
    if len(dimensions) != 10 or len(set(dimensions)) != 10:
        errors.append("catalog must define exactly ten unique evidence dimensions")
    if len(features) != 9:
        errors.append(f"catalog must define nine feature families; found {len(features)}")
    for feature in features:
        feature_id = feature.get("feature_id") or "<missing>"
        controls = feature.get("controls") or {}
        for control in ("kill_switch", "rollback", "degraded_behavior"):
            if not controls.get(control):
                errors.append(f"{feature_id}: missing {control} control")
        if (
            feature.get("implementation_status") == "not_implemented"
            and feature.get("maximum_stage") != "disabled"
        ):
            errors.append(f"{feature_id}: unimplemented feature is not disabled")

    commands = [
        [
            sys.executable,
            "scripts/run_sqlite_memory_tests.py",
            "apps.platform_runtime.tests.test_intelligence_promotion",
            "apps.platform_runtime.tests.test_layout_observability_context",
            "apps.platform_runtime.tests.test_layout_observability",
            "apps.platform_runtime.tests.test_rum_ingest",
            "apps.platform_runtime.tests.test_rum_aggregate",
            "--verbosity=1",
        ],
        [
            sys.executable,
            "manage.py",
            "verify_intelligence_promotion",
            "--stage",
            "repository_verified",
            "--write-report",
            str(REPORT.relative_to(ROOT)),
        ],
        [sys.executable, "manage.py", "check"],
    ]
    env = os.environ.copy()
    env.setdefault("RMC_TEST_LOCAL_SQLITE", "1")
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        if result.returncode:
            errors.append(f"verification command failed: {' '.join(command)}")

    if not REPORT.is_file():
        errors.append("repository readiness report was not generated")
    else:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        if report.get("eligible_count") != 9 or report.get("blocked_count") != 0:
            errors.append(
                "repository report must contain nine eligible and zero blocked families"
            )
        blocked = {
            row.get("feature_id")
            for row in report.get("decisions") or []
            if not row.get("eligible")
        }
        if blocked:
            errors.append(f"unexpected repository blockers: {sorted(blocked)}")

    if errors:
        print("INTELLIGENCE_PROMOTION_CONTRACT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("INTELLIGENCE_PROMOTION_CONTRACT_PASS eligible=9 blocked=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
