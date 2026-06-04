#!/usr/bin/env python3
"""AWS pillar: no bare is_staff bypass in tenant guard modules without host gate."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "var" / "security-audit-baseline-staff-bypass-tenant-guards.json"

TARGETS = (
    ROOT / "apps" / "schools" / "tenant_api_guards.py",
    ROOT / "apps" / "migration_cloud" / "api" / "permissions.py",
)

_BAD = re.compile(
    r"if\s+.*\bis_staff\b.*:\s*\n\s*return\s+True",
    re.MULTILINE,
)


def _scan() -> list[str]:
    findings: list[str] = []
    for path in TARGETS:
        if not path.is_file():
            findings.append(f"missing:{path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        if _BAD.search(text):
            findings.append(f"bare-is_staff-bypass:{path.relative_to(ROOT)}")
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel == "apps/schools/tenant_api_guards.py":
            if "staff_may_bypass_tenant_guard_on_request" not in text:
                findings.append(f"missing-host-gate-helper:{rel}")
        if rel == "apps/migration_cloud/api/permissions.py":
            if "_is_operator_shell_request" not in text:
                findings.append(f"missing-operator-shell-helper:{rel}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()
    findings = _scan()
    if args.update_baseline:
        import json
        from datetime import datetime, timezone

        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {
                    "finding_count": len(findings),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "findings": findings,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"baseline updated: {len(findings)} findings")
        return 0
    if args.compare and BASELINE.is_file():
        import json

        data = json.loads(BASELINE.read_text(encoding="utf-8"))
        expected = int(data.get("finding_count", 0))
        if len(findings) != expected:
            print(
                f"scan_staff_bypass_tenant_guards: drift {len(findings)} vs baseline {expected}",
                file=sys.stderr,
            )
            for f in findings:
                print(f"  {f}", file=sys.stderr)
            return 1
    elif findings:
        for f in findings:
            print(f, file=sys.stderr)
        print(f"scan_staff_bypass_tenant_guards: {len(findings)} FAIL", file=sys.stderr)
        return 1
    print("scan_staff_bypass_tenant_guards: OK (0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
