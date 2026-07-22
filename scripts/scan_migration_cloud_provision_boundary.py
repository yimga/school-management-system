#!/usr/bin/env python3
"""AST gate: Migration Cloud must never create schools via provision dispatch.

School-first boundary — MC intake/landers require an existing school FK.
A new ``dispatch_provision_school`` / ``complete_provisioning_for_school`` /
``provision_school_sync`` call under ``apps/migration_cloud/`` fails CI.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MC_ROOT = ROOT / "apps" / "migration_cloud"
BASELINE = ROOT / "var" / "security-audit-baseline-migration-cloud-provision-boundary.json"

FORBIDDEN = frozenset(
    {
        "dispatch_provision_school",
        "complete_provisioning_for_school",
        "provision_school_sync",
        "kick_complete_provisioning_background",
        "provision_school_task",
    }
)


def _iter_py_files(root: Path):
    for path in root.rglob("*.py"):
        if "migrations" in path.parts or "tests" in path.parts:
            continue
        yield path


def scan() -> list[dict]:
    findings: list[dict] = []
    if not MC_ROOT.is_dir():
        return findings
    for path in _iter_py_files(MC_ROOT):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            findings.append(
                {
                    "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "name": "<syntax>",
                    "line": getattr(exc, "lineno", 0) or 0,
                    "detail": str(exc),
                }
            )
            continue
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in FORBIDDEN:
                        findings.append(
                            {
                                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                                "name": alias.name,
                                "line": node.lineno,
                                "detail": "import",
                            }
                        )
                continue
            if name in FORBIDDEN:
                findings.append(
                    {
                        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "name": name,
                        "line": getattr(node, "lineno", 0) or 0,
                        "detail": "reference",
                    }
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args(argv)

    findings = scan()
    payload = {
        "finding_count": len(findings),
        "findings": findings,
        "rule": "migration_cloud_must_not_dispatch_school_provision",
    }

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline {BASELINE} count={len(findings)}")
        return 0

    if args.compare and BASELINE.is_file():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        expected = int(baseline.get("finding_count", 0))
        if len(findings) != expected:
            print(
                f"MIGRATION_CLOUD_PROVISION_BOUNDARY_FAIL: count {len(findings)} "
                f"!= baseline {expected}"
            )
            if args.json:
                print(json.dumps(payload, indent=2))
            return 1
        print(
            f"MIGRATION_CLOUD_PROVISION_BOUNDARY_PASS: {len(findings)} findings "
            f"(baseline {expected})"
        )
        return 0

    if findings:
        print(f"MIGRATION_CLOUD_PROVISION_BOUNDARY_FAIL: {len(findings)} hit(s)")
        for row in findings[:20]:
            print(f"  {row['path']}:{row['line']} {row['name']} ({row['detail']})")
        if args.json:
            print(json.dumps(payload, indent=2))
        return 1

    print("MIGRATION_CLOUD_PROVISION_BOUNDARY_PASS: 0 findings")
    if args.json:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
