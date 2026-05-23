#!/usr/bin/env python3
"""Fail CI when actions/upload-artifact omits retention-days or exceeds 3 days."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
MAX_DAYS = 3


def audit_file(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    issues: list[str] = []
    i = 0
    while i < len(lines):
        if not re.search(r"uses:\s+actions/upload-artifact@v", lines[i]):
            i += 1
            continue
        if i + 1 >= len(lines) or lines[i + 1].strip() != "with:":
            issues.append(f"{path.name}:{i + 1}: upload-artifact missing with: block")
            i += 1
            continue
        j = i + 2
        block: list[str] = []
        while j < len(lines):
            line = lines[j]
            if line.startswith("          ") or line.strip() == "":
                block.append(line)
                j += 1
                continue
            if line.startswith("        ") and not line.startswith("          "):
                # sibling keys under step (if:, env:, etc.) — still part of step
                break
            break
        has = False
        days = None
        for line in block:
            m = re.match(r"\s+retention-days:\s*(\d+)", line)
            if m:
                has = True
                days = int(m.group(1))
        if not has:
            issues.append(
                f"{path.name}:{i + 1}: upload-artifact must set retention-days (use 1)"
            )
        elif days is not None and days > MAX_DAYS:
            issues.append(
                f"{path.name}:{i + 1}: retention-days={days} exceeds max {MAX_DAYS}"
            )
        i = j
    return issues


def main() -> int:
    all_issues: list[str] = []
    count = 0
    for path in sorted(WORKFLOWS.glob("*.yml")):
        if "upload-artifact" not in path.read_text(encoding="utf-8"):
            continue
        blocks_before = len(all_issues)
        all_issues.extend(audit_file(path))
        if len(all_issues) == blocks_before:
            # count blocks in file
            text = path.read_text(encoding="utf-8")
            count += len(re.findall(r"uses:\s+actions/upload-artifact@v", text))

    if all_issues:
        for msg in all_issues:
            print(f"FAIL: {msg}")
        print(f"\nGITHUB_ARTIFACT_RETENTION_FAIL ({len(all_issues)} issues)")
        return 1
    print(f"GITHUB_ARTIFACT_RETENTION_PASS ({count} upload-artifact blocks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
