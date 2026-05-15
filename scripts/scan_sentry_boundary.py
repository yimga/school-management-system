#!/usr/bin/env python
"""Sentry SDK boundary scanner.

Enforces the platform rule: app code must NEVER import ``sentry_sdk``
directly. Every Sentry interaction (transactions, tags, spans, breadcrumbs)
must go through the helpers in ``apps.observability.tracing``:

    start_named_transaction / set_transaction_status / finish_transaction
    trace_view (decorator)
    set_tags (scope-level tagging)

This keeps the SDK import-fenced to a single bounded context, makes the
"is Sentry installed?" / "is the DSN set?" degradation logic uniform,
and means swapping observability providers (OpenTelemetry, etc.) is a
one-file edit.

Output mirrors ``scan_ai_gateway_boundary.py``:

  * ``python scripts/scan_sentry_boundary.py``        — write baseline
  * ``python scripts/scan_sentry_boundary.py --compare`` — diff vs baseline (CI gate)
  * ``python scripts/scan_sentry_boundary.py --json``    — print JSON payload

Baseline: ``var/security-audit-baseline-sentry-boundary.json``.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = REPO_ROOT / "apps"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-sentry-boundary.json"

FORBIDDEN_MODULE = "sentry_sdk"

# Only the observability bounded context imports sentry_sdk directly.
# Everything under ``apps/observability/`` is allowlisted; everything
# else is a violation.
ALLOWED_PATH_PREFIXES = (
    "apps/observability/",
)

EXCLUDE_DIR_NAMES = {"__pycache__", "node_modules", "migrations"}
EXCLUDE_FILE_SUFFIXES = ("_test.py", "_tests.py")


def _iter_python_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
            continue
        if "tests" in rel_parts:
            continue
        if path.name.endswith(EXCLUDE_FILE_SUFFIXES):
            continue
        yield path


def _is_allowed(rel_path: str) -> bool:
    return any(rel_path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES)


def _imports_forbidden(tree: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == FORBIDDEN_MODULE or alias.name.startswith(
                    FORBIDDEN_MODULE + "."
                ):
                    hits.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == FORBIDDEN_MODULE or module.startswith(
                FORBIDDEN_MODULE + "."
            ):
                names = ", ".join(alias.name for alias in node.names)
                hits.append((node.lineno, f"from {module} import {names}"))
    return hits


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for path in _iter_python_files(APPS_DIR):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if _is_allowed(rel):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for lineno, statement in _imports_forbidden(tree):
            findings.append(
                {"path": rel, "line": lineno, "statement": statement}
            )
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "forbidden_module": FORBIDDEN_MODULE,
        "allowed_path_prefixes": list(ALLOWED_PATH_PREFIXES),
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
    print(f"Sentry boundary scan: {len(findings)} violation(s)")
    if not findings:
        print("  (clean — sentry_sdk is fenced inside apps/observability/)")
        return
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
    baseline_set = {
        (item["path"], item["statement"]) for item in baseline.get("findings", [])
    }
    current_set = {(item["path"], item["statement"]) for item in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    _print_summary(findings)
    if new:
        print("\nNEW violations introduced (boundary regression):")
        for path, statement in sorted(new):
            print(f"  {path}  {statement}")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, statement in sorted(removed):
            print(f"  {path}  {statement}")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true", help="Diff against baseline (CI mode).")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload to stdout.")
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
