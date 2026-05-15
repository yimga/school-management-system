#!/usr/bin/env python
"""`assert` statements in production-code boundary scanner.

Flags any ``assert`` statement that lives in production-loaded code
under ``apps/`` and ``services/``.

Why this matters: ``assert`` statements are stripped when Python runs
under ``python -O`` (optimized mode). Anything load-bearing — a guard,
a validation step, an invariant check — becomes a silent no-op in
production. ``assert`` is fine for tests (which never run under -O)
but is a latent reliability bug everywhere else.

Excluded paths:
  - ``tests/`` directories (pytest assertions are the entire point)
  - ``migrations/`` (asserts only run at migration time, single-shot)
  - ``management/commands/`` (operator-run, controlled environment)

Allowlist: load-bearing asserts that are intentional (e.g. a type
narrowing hint for static analysis with a follow-on real check) can
be marked with ``# assert-allow: <reason>`` on the same line. Use
sparingly — the right fix is almost always ``if not …: raise ValueError``.

Output mirrors the other boundary scanners.
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
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-assert-in-production.json"

EXCLUDED_DIR_SEGMENTS = frozenset({"tests", "migrations"})
EXCLUDED_PATH_FRAGMENTS = ("management/commands/",)
# Pytest-style test files colocated with production code.
EXCLUDED_FILENAME_PREFIXES = ("test_",)
EXCLUDED_FILENAME_SUFFIXES = ("_tests.py", "_test.py")

ALLOW_MARKER = "assert-allow:"


def _iter_py_files():
    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            parts = set(path.relative_to(REPO_ROOT).parts)
            if parts & EXCLUDED_DIR_SEGMENTS:
                continue
            if any(fragment in rel for fragment in EXCLUDED_PATH_FRAGMENTS):
                continue
            name = path.name
            if any(name.startswith(p) for p in EXCLUDED_FILENAME_PREFIXES):
                continue
            if any(name.endswith(s) for s in EXCLUDED_FILENAME_SUFFIXES):
                continue
            yield path


def _is_allowlisted(source_lines: list[str], lineno: int) -> bool:
    idx = lineno - 1
    if 0 <= idx < len(source_lines) and ALLOW_MARKER in source_lines[idx]:
        return True
    return False


def _snippet(source_lines: list[str], lineno: int) -> str:
    idx = lineno - 1
    if 0 <= idx < len(source_lines):
        return source_lines[idx].strip()
    return ""


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for path in _iter_py_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        source_lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue
            if _is_allowlisted(source_lines, node.lineno):
                continue
            findings.append(
                {
                    "path": rel,
                    "line": node.lineno,
                    "snippet": _snippet(source_lines, node.lineno),
                }
            )
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "assert statements are stripped under python -O; use explicit raise in production code",
        "scan_dirs": [d.relative_to(REPO_ROOT).as_posix() for d in SCAN_DIRS],
        "excluded_dir_segments": sorted(EXCLUDED_DIR_SEGMENTS),
        "excluded_path_fragments": list(EXCLUDED_PATH_FRAGMENTS),
        "excluded_filename_prefixes": list(EXCLUDED_FILENAME_PREFIXES),
        "excluded_filename_suffixes": list(EXCLUDED_FILENAME_SUFFIXES),
        "allow_marker": ALLOW_MARKER,
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
    print(f"assert-in-production scan: {len(findings)} assert statement(s)")
    for finding in findings:
        print(f"  {finding['path']}:{finding['line']}  {finding['snippet']}")


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
    baseline_set = {
        (item["path"], item["line"]) for item in baseline.get("findings", [])
    }
    current_set = {(item["path"], item["line"]) for item in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    _print_summary(findings)
    if new:
        print("\nNEW assert statements introduced:")
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
