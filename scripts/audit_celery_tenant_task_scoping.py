#!/usr/bin/env python3
"""AWS P1: Celery task modules must scope tenant querysets or document cross-tenant reads."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "var" / "security-audit-baseline-celery-tenant-task-scoping.json"

_FILTER_RE = re.compile(
    r"\.objects\.(?:filter|get|exclude|all|update|delete)\(",
)
_SCHOOL_RE = re.compile(r"\bschool(_id)?\s*=")
_ALLOW_RE = re.compile(
    r"#\s*tenant-isolation-allow:\s*\S",
)


def _scan_file(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    if "/tests/" in rel or "/migrations/" in rel:
        return []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: list[str] = []
    for idx, line in enumerate(lines):
        if not _FILTER_RE.search(line):
            continue
        if _SCHOOL_RE.search(line):
            continue
        window = "\n".join(lines[max(0, idx - 2) : idx + 1])
        if _ALLOW_RE.search(window):
            continue
        findings.append(f"{rel}:{idx + 1}:{line.strip()[:100]}")
    return findings


def _scan() -> list[str]:
    findings: list[str] = []
    for path in sorted(ROOT.glob("apps/**/tasks*.py")):
        findings.extend(_scan_file(path))
    for path in sorted(ROOT.glob("apps/**/tasks/**/*.py")):
        findings.extend(_scan_file(path))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()
    findings = _scan()
    if args.update_baseline:
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
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
        expected = int(data.get("finding_count", 0))
        if len(findings) != expected:
            print(
                f"audit_celery_tenant_task_scoping: drift {len(findings)} vs baseline {expected}",
                file=sys.stderr,
            )
            for item in findings[:40]:
                print(f"  {item}", file=sys.stderr)
            if len(findings) > 40:
                print(f"  ... and {len(findings) - 40} more", file=sys.stderr)
            return 1
    elif args.compare and not BASELINE.is_file():
        print(
            "audit_celery_tenant_task_scoping: missing baseline "
            "(run --update-baseline after review)",
            file=sys.stderr,
        )
        return 1
    elif findings:
        for item in findings[:40]:
            print(item, file=sys.stderr)
        print(f"audit_celery_tenant_task_scoping: {len(findings)} findings", file=sys.stderr)
        return 1
    print("audit_celery_tenant_task_scoping: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
