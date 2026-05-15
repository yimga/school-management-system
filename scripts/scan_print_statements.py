#!/usr/bin/env python
"""print() statement scanner.

Enforces the rule: production code (under ``apps/`` and ``services/``)
must NEVER call ``print()``. All output goes through ``logging`` so that
log levels, structured fields, and Sentry breadcrumbs work uniformly.

Allowlist: management commands legitimately use ``self.stdout.write(...)``
and occasionally ``print()`` for human-facing CLI output. Test files are
excluded. Migration files are excluded (rare ``print`` from data migrations
is acceptable for one-shot operator visibility).

Output mirrors the other boundary scanners:

  * ``python scripts/scan_print_statements.py``        — write baseline
  * ``python scripts/scan_print_statements.py --compare`` — diff vs baseline (CI)
  * ``python scripts/scan_print_statements.py --json``    — JSON to stdout
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (REPO_ROOT / "apps", REPO_ROOT / "services")
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-print-statements.json"

EXCLUDE_DIR_NAMES = {"__pycache__", "node_modules", "migrations", "tests", "management"}
EXCLUDE_FILE_SUFFIXES = ("_test.py", "_tests.py")


def _iter_python_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
            continue
        if path.name.endswith(EXCLUDE_FILE_SUFFIXES):
            continue
        yield path


def _print_calls(tree: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                hits.append((node.lineno, "print(...)"))
    return hits


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for root in SCAN_DIRS:
        for path in _iter_python_files(root):
            rel = path.relative_to(REPO_ROOT).as_posix()
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, OSError, UnicodeDecodeError):
                continue
            for lineno, statement in _print_calls(tree):
                findings.append(
                    {"path": rel, "line": lineno, "statement": statement}
                )
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "no print() in apps/ or services/ outside management commands and tests",
        "scan_dirs": [d.relative_to(REPO_ROOT).as_posix() for d in SCAN_DIRS],
        "exclude_dir_names": sorted(EXCLUDE_DIR_NAMES),
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
    print(f"print() scan: {len(findings)} call(s)")
    for finding in findings:
        print(f"  {finding['path']}:{finding['line']}  {finding['statement']}")


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
    baseline_set = {(item["path"], item["line"]) for item in baseline.get("findings", [])}
    current_set = {(item["path"], item["line"]) for item in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    _print_summary(findings)
    if new:
        print("\nNEW print() calls introduced:")
        for path, line in sorted(new):
            print(f"  {path}:{line}")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, line in sorted(removed):
            print(f"  {path}:{line}")
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
