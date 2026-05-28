#!/usr/bin/env python
"""REST-bypass scanner for the WAL stream (v4.00.0 zero-tolerance gate).

Once the WAL outbox is the canonical write path for mass-action domains
(attendance, grades, billing charges, communication sends), any view that
directly calls ``AttendanceRecord.objects.create``/``bulk_create``/``update``
from a request-path module bypasses the WAL contract and re-introduces the
8:00 AM thundering-herd. This scanner flags those calls.

Allowlist: ``apps/wal_stream/*`` (the canonical writer) +
``apps/*/management/commands/*`` (admin/CLI tools).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_ROOT = REPO_ROOT / "apps"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-rest-attendance-writes.json"

EXCLUDE_DIR_NAMES = {"__pycache__", "node_modules", "migrations", "tests", "management", "wal_stream"}
WATCHED_MODELS = ("AttendanceRecord", "GradeEntry", "BillingCharge")
WATCHED_METHODS = ("create", "bulk_create", "update", "update_or_create")


def _iter_python_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
            continue
        yield path


def _hits(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Look for <Model>.objects.<method>(...)
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in WATCHED_METHODS:
            continue
        # func.value is the .objects manager access
        if not isinstance(func.value, ast.Attribute) or func.value.attr != "objects":
            continue
        # func.value.value is the model name
        model_node = func.value.value
        model_name = None
        if isinstance(model_node, ast.Name):
            model_name = model_node.id
        elif isinstance(model_node, ast.Attribute):
            model_name = model_node.attr
        if model_name in WATCHED_MODELS:
            yield (node.lineno, f"{model_name}.objects.{func.attr}(...)")


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    if not APPS_ROOT.exists():
        return findings
    for path in _iter_python_files(APPS_ROOT):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for lineno, statement in _hits(tree):
            findings.append({
                "path": path.relative_to(REPO_ROOT).as_posix(),
                "line": lineno,
                "statement": statement,
                "reason": "bypasses rmcWAL outbox; route mass actions through /ws/wal/",
            })
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings):
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "mass-action models must be written via apps.wal_stream, not direct ORM in views",
        "scan_dirs": ["apps"],
        "watched_models": list(WATCHED_MODELS),
        "watched_methods": list(WATCHED_METHODS),
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_baseline():
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_summary(findings):
    print(f"rest_attendance_writes scan: {len(findings)} bypass(es)")
    for f in findings:
        print(f"  {f['path']}:{f['line']}  {f['statement']}")


def _write_baseline(findings):
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _compare(findings):
    baseline = _load_baseline()
    if baseline is None:
        _print_summary(findings)
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_set = {(f["path"], f["line"]) for f in baseline.get("findings", [])}
    current_set = {(f["path"], f["line"]) for f in findings}
    new = current_set - baseline_set
    _print_summary(findings)
    if new:
        print("\nNEW REST bypasses of the WAL outbox:")
        for p, ln in sorted(new):
            print(f"  {p}:{ln}")
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
