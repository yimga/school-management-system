#!/usr/bin/env python3
"""Phase 0X verifier: regulatory_matrix block on every country shard."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"
OUT_PATH = REPO / "docs" / "generated" / "regulatory_matrix_coverage_audit.json"

REQUIRED_KEYS = (
    "student_privacy_regimes",
    "age_of_digital_consent",
    "biometric_data_rule",
    "ai_regulation",
    "sms_telecom_rule",
    "tax_reporting_obligations",
    "sanctions_status",
    "records_retention_years",
    "content_safety_regime",
    "accessibility_statute",
)


def _audit() -> tuple[int, list[str], dict[str, int]]:
    failures: list[str] = []
    coverage: dict[str, int] = {key: 0 for key in REQUIRED_KEYS}
    shard_paths = sorted(SHARD_DIR.glob("*.json")) if SHARD_DIR.is_dir() else []
    if not shard_paths:
        return 0, ["no shards found under docs/generated/country_governance_matrix/"], coverage

    for path in shard_paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{path.name}: invalid JSON ({exc})")
            continue
        iso = str(data.get("iso_alpha2") or path.stem)
        block = data.get("regulatory_matrix")
        if not isinstance(block, dict):
            failures.append(f"{iso}: missing regulatory_matrix block")
            continue
        for key in REQUIRED_KEYS:
            if key not in block:
                failures.append(f"{iso}: regulatory_matrix.{key} missing")
            else:
                coverage[key] += 1
    return len(shard_paths), failures, coverage


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0X regulatory matrix coverage gate")
    parser.add_argument("--json", action="store_true", help="Write audit JSON")
    args = parser.parse_args()

    total, failures, coverage = _audit()
    verdict = "REGULATORY_MATRIX_COVERAGE_PASS" if not failures else "REGULATORY_MATRIX_COVERAGE_FAIL"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "shard_total": total,
        "finding_count": len(failures),
        "coverage_per_key": coverage,
        "failures": failures[:80],
    }
    if args.json:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(f"verify_regulatory_matrix_coverage: {verdict} ({len(failures)} findings)", file=sys.stderr)
        for line in failures[:20]:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"verify_regulatory_matrix_coverage: {verdict} ({total} shards)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
