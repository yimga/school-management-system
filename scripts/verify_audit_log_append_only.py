#!/usr/bin/env python3
"""Verify compliance AuditLog is append-only in application code (no .update/.delete)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = (ROOT / "apps", ROOT / "services")
ALLOW_SUFFIXES = ("/migrations/", "/tests/", "/management/commands/")


def _scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return findings
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        chain = []
        cur = func
        while isinstance(cur, ast.Attribute):
            chain.insert(0, cur.attr)
            cur = cur.value
        if not chain:
            continue
        if chain[-2:] == ["objects", "update"] or chain[-2:] == ["objects", "delete"]:
            model_hint = ""
            if isinstance(cur, ast.Name):
                model_hint = cur.id
            if "AuditLog" in model_hint or (
                len(chain) >= 3 and chain[0] == "AuditLog"
            ):
                findings.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} AuditLog.{chain[-1]}()"
                )
    return findings


def main() -> int:
    findings: list[str] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            rel = path.as_posix()
            if any(seg in rel for seg in ALLOW_SUFFIXES):
                continue
            findings.extend(_scan_file(path))
    if findings:
        print("verify_audit_log_append_only: FAIL", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("verify_audit_log_append_only: PASS (no AuditLog.objects.update/delete in app code)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
