#!/usr/bin/env python3
"""Exam-board local-first filtering gate.

Flags UI/form code that presents the full global ``Board.choices`` list instead
of routing through ``apps.academics.exam_boards.allowed_board_choices(country_code)``.

Model field ``choices=Board.choices`` on the ORM schema is exempt (DB validation).
The SOT module ``exam_boards.py`` is exempt.

Mark intentional sites with ``# exam-board-filter-allow: <reason>`` or
``<!-- exam-board-filter-allow: <reason> -->`` on the same line or line above.

Run:
  python scripts/scan_exam_board_filtering.py
  python scripts/scan_exam_board_filtering.py --compare
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = REPO_ROOT / "apps"
TEMPLATES_DIR = REPO_ROOT / "templates"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-exam-board-filtering.json"

ALLOW_MARKER = "exam-board-filter-allow:"
PATTERN = re.compile(
    r"(?:CertificationExamSession\.)?Board\.choices",
    re.MULTILINE,
)

EXEMPT_REL_PATHS = frozenset(
    {
        "apps/academics/exam_boards.py",
        "apps/academics/models.py",
        "apps/academics/tests/test_exam_boards.py",
    }
)
EXCLUDED_SEGMENTS = frozenset({"migrations", "tests"})
EXCLUDED_TAILS = frozenset({("management", "commands")})


def _is_excluded(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    if rel in EXEMPT_REL_PATHS:
        return True
    if rel.startswith("templates/"):
        return False
    if not rel.startswith("apps/") or not rel.endswith(".py"):
        return True
    parts = Path(rel).parts
    if any(seg in EXCLUDED_SEGMENTS for seg in parts):
        return True
    for i in range(len(parts) - 1):
        if (parts[i], parts[i + 1]) in EXCLUDED_TAILS:
            return True
    return False


def _is_allowlisted(lines: list[str], lineno: int) -> bool:
    for offset in (0, -1):
        idx = lineno - 1 + offset
        if 0 <= idx < len(lines) and ALLOW_MARKER in lines[idx]:
            return True
    return False


def _scan_file(path: Path) -> list[dict]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    findings: list[dict] = []
    for match in PATTERN.finditer(text):
        lineno = text.count("\n", 0, match.start()) + 1
        if _is_allowlisted(lines, lineno):
            continue
        findings.append({"path": rel, "line": lineno, "match": match.group(0)})
    return findings


def _scan() -> list[dict]:
    findings: list[dict] = []
    for base in (APPS_DIR, TEMPLATES_DIR):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in {".py", ".html"}:
                continue
            if _is_excluded(path):
                continue
            findings.extend(_scan_file(path))
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "Board selection UI must filter via allowed_board_choices(country_code); "
            "never iterate Board.choices directly outside schema/SOT."
        ),
        "allow_marker": ALLOW_MARKER,
        "exempt_paths": sorted(EXEMPT_REL_PATHS),
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_summary(findings: list[dict]) -> None:
    print(f"Exam-board filtering scan: {len(findings)} unfiltered Board.choices site(s)")
    for item in findings[:40]:
        print(f"  {item['path']}:{item['line']}  {item['match']}")
    if len(findings) > 40:
        print(f"  ... and {len(findings) - 40} more (see --json)")


def _write_baseline(findings: list[dict]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _compare(findings: list[dict]) -> int:
    baseline = _load_baseline()
    if baseline is None:
        _print_summary(findings)
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_counts = Counter((item["path"], item["line"]) for item in baseline.get("findings", []))
    current_counts = Counter((item["path"], item["line"]) for item in findings)
    new = current_counts - baseline_counts
    removed = baseline_counts - current_counts
    _print_summary(findings)
    if new:
        print("\nNEW unfiltered Board.choices site(s):")
        for (path, line), count in sorted(new.items()):
            print(f"  {path}:{line}  +{count}")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for (path, line), count in sorted(removed.items()):
            print(f"  {path}:{line}  -{count}")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = _scan()
    if args.json:
        print(json.dumps(_baseline_payload(findings), indent=2, sort_keys=True))
        return 0
    if args.compare:
        return _compare(findings)
    _print_summary(findings)
    _write_baseline(findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
