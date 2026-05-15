#!/usr/bin/env python
"""Magic-number boundary scanner.

Flags integer literals where ``abs(value) >= 100`` that appear in
production code paths under ``apps/`` and ``services/`` — i.e. values
that look like they encode a business rule (timeouts in seconds,
batch sizes, retention windows, default page sizes, rate-limit caps,
…) but are inlined rather than routed through the 7-layer
configurability contract.

The threshold of 100 deliberately excludes the very small constants
(-99..99) that cover the bulk of innocuous arithmetic — booleans,
small counts, percentages, HTTP status fragments. The intent is
drift-detection, not zero-debt: every entry in the baseline is a
candidate for promotion to ``RuntimeDefaults`` / a ``constants.py``
module / a tenant ``SiteSettings`` field.

Excluded contexts:
  - test files (any ``tests/`` dir)
  - migrations (historical migration values are frozen)
  - fixtures (data files)
  - management commands (operator-run)
  - module-level assignments in ``config/``, ``settings/``,
    ``constants.py``, or ``constants/*.py`` (the right home for constants)
  - common scale literals: 0, 1, -1, 2, 10, 100, 1000
  - 4-digit years (1900..2100) — these read as dates, not magic numbers

Allowlist: ``# magic-number-allow: <reason>`` on the same line as
the literal.
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
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-magic-numbers.json"

EXCLUDED_DIR_SEGMENTS = frozenset({"tests", "migrations", "fixtures"})
EXCLUDED_PATH_FRAGMENTS = ("management/commands/",)
# Test files alongside production code: ``test_*.py`` and ``*_tests.py``.
EXCLUDED_FILENAME_PREFIXES = ("test_",)
EXCLUDED_FILENAME_SUFFIXES = ("_tests.py", "_test.py")

# Path fragments that indicate "this is the right home for constants"
CONSTANTS_HOME_FRAGMENTS = ("/config/", "/settings/", "/constants/")
CONSTANTS_HOME_FILENAMES = frozenset({"constants.py", "settings.py", "config.py"})

# Whitelisted scale literals
_SCALE_LITERALS = frozenset({0, 1, -1, 2, 10, 100, 1000})

# RFC-defined HTTP status codes. These are universally understood, not
# "magic" — `Response(status=404)` is more readable than
# `Response(status=HTTPStatus.NOT_FOUND)` at most call sites, and they
# don't drift the way business-rule constants do. Drift detection on
# these would be pure noise.
_HTTP_STATUS_CODES = frozenset({
    # 2xx success
    200, 201, 202, 203, 204, 205, 206, 207, 208, 226,
    # 3xx redirection
    300, 301, 302, 303, 304, 305, 307, 308,
    # 4xx client error
    400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411, 412, 413,
    414, 415, 416, 417, 418, 421, 422, 423, 424, 425, 426, 428, 429, 431, 451,
    # 5xx server error
    500, 501, 502, 503, 504, 505, 506, 507, 508, 510, 511,
})

ALLOWED_LITERALS = _SCALE_LITERALS | _HTTP_STATUS_CODES

THRESHOLD = 100
YEAR_MIN = 1900
YEAR_MAX = 2100

ALLOW_MARKER = "magic-number-allow:"


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


def _is_constants_home(rel_path: str, filename: str) -> bool:
    if filename in CONSTANTS_HOME_FILENAMES:
        return True
    if any(fragment in f"/{rel_path}" for fragment in CONSTANTS_HOME_FRAGMENTS):
        return True
    return False


def _is_allowlisted(source_lines: list[str], lineno: int) -> bool:
    idx = lineno - 1
    if 0 <= idx < len(source_lines) and ALLOW_MARKER in source_lines[idx]:
        return True
    return False


def _snippet(source_lines: list[str], lineno: int) -> str:
    idx = lineno - 1
    if 0 <= idx < len(source_lines):
        return source_lines[idx].strip()[:200]
    return ""


def _extract_int_value(node: ast.AST) -> int | None:
    """Return integer value for a Constant int or UnaryOp(-/+, Constant int)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = node.operand
        if isinstance(inner, ast.Constant) and isinstance(inner.value, int) and not isinstance(inner.value, bool):
            return -inner.value if isinstance(node.op, ast.USub) else inner.value
    return None


def _is_year(value: int) -> bool:
    return YEAR_MIN <= value <= YEAR_MAX


def _collect_module_level_assignment_lines(tree: ast.Module) -> set[int]:
    """Lines that belong to module-level (Assign/AnnAssign) targets."""
    lines: set[int] = set()
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            # Cover the value subtree by line range
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            for ln in range(start, end + 1):
                lines.add(ln)
    return lines


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for path in _iter_py_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        filename = path.name
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        source_lines = source.splitlines()
        constants_home = _is_constants_home(rel, filename)
        module_assign_lines = _collect_module_level_assignment_lines(tree)

        # Walk the tree and find every int constant.
        # Track parents so we can skip the inner Constant of a UnaryOp
        # (we already account for the negative as a whole).
        skip_nodes: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
                if isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, int):
                    skip_nodes.add(id(node.operand))

        for node in ast.walk(tree):
            if id(node) in skip_nodes:
                continue
            value = _extract_int_value(node)
            if value is None:
                continue
            if value in ALLOWED_LITERALS:
                continue
            if abs(value) < THRESHOLD:
                continue
            if _is_year(value):
                continue
            lineno = node.lineno
            # If this is a module-level assignment AND we're in a constants home,
            # this is the correct location — skip.
            if constants_home and lineno in module_assign_lines:
                continue
            if _is_allowlisted(source_lines, lineno):
                continue
            findings.append(
                {
                    "path": rel,
                    "line": lineno,
                    "value": value,
                    "snippet": _snippet(source_lines, lineno),
                }
            )
    findings.sort(key=lambda item: (item["path"], item["line"], item["value"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "Integer literals with abs(value) >= 100 in production code should route through "
            "the 7-layer configurability contract (RuntimeDefaults / constants.py / SiteSettings)"
        ),
        "scan_dirs": [d.relative_to(REPO_ROOT).as_posix() for d in SCAN_DIRS],
        "threshold": THRESHOLD,
        "allowed_literals": sorted(ALLOWED_LITERALS),
        "year_range_excluded": [YEAR_MIN, YEAR_MAX],
        "excluded_dir_segments": sorted(EXCLUDED_DIR_SEGMENTS),
        "excluded_path_fragments": list(EXCLUDED_PATH_FRAGMENTS),
        "excluded_filename_prefixes": list(EXCLUDED_FILENAME_PREFIXES),
        "excluded_filename_suffixes": list(EXCLUDED_FILENAME_SUFFIXES),
        "constants_home_fragments": list(CONSTANTS_HOME_FRAGMENTS),
        "constants_home_filenames": sorted(CONSTANTS_HOME_FILENAMES),
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
    print(f"magic-numbers scan: {len(findings)} integer literal(s) flagged")
    for finding in findings[:50]:
        print(f"  {finding['path']}:{finding['line']}  ({finding['value']})  {finding['snippet']}")
    if len(findings) > 50:
        print(f"  ... and {len(findings) - 50} more")


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
        (item["path"], item["line"], item["value"]) for item in baseline.get("findings", [])
    }
    current_set = {(item["path"], item["line"], item["value"]) for item in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    _print_summary(findings)
    if new:
        print("\nNEW magic numbers introduced:")
        for path, line, value in sorted(new):
            print(f"  {path}:{line}  ({value})")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, line, value in sorted(removed):
            print(f"  {path}:{line}  ({value})")
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
