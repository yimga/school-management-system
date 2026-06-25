#!/usr/bin/env python
"""Verify every registered workflow has a healing chain or explicit operator-only flag."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-workflow-healing-coverage.json"


def main(argv: list[str] | None = None) -> int:
    import os
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    os.chdir(REPO_ROOT)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from apps.platform_runtime.workflow_healing_chains import healing_coverage_report

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)

    report = healing_coverage_report()
    gaps = list(report.get("gaps") or [])
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(gaps),
        "workflow_count": report.get("workflow_count", 0),
        "covered_count": report.get("covered_count", 0),
        "gaps": gaps,
    }

    if args.write_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline: {BASELINE_PATH} ({len(gaps)} gaps)")

    if args.json:
        print(json.dumps(payload, indent=2))
    elif gaps:
        print("WORKFLOW_HEALING_COVERAGE_GAPS:")
        for gap in gaps[:40]:
            print(f"  - {gap}")
        if len(gaps) > 40:
            print(f"  ... and {len(gaps) - 40} more")
    else:
        print(
            f"WORKFLOW_HEALING_COVERAGE_PASS "
            f"({report.get('covered_count', 0)}/{report.get('workflow_count', 0)} workflows)"
        )

    if args.strict and gaps:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
