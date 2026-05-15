#!/usr/bin/env python
"""AI gateway boundary scanner.

Enforces the platform rule: app code (anything under ``apps/``) must NEVER
import ``services.ai_gateway`` directly. Every AI call from app code must
go through ``services.ai_helpers`` (``invoke_with_request`` /
``invoke_task`` / ``record_feedback``), which wraps the gateway with
graceful degradation, PII inference, and stable prompt-type tagging.

A small allowlist of *infrastructure* modules is permitted to import the
gateway directly — they are the layers that ``ai_helpers`` itself
delegates to, or that expose ops/admin surfaces over the gateway
internals. Anything else is a boundary violation.

Output mirrors ``scan_tenant_queryset_safety.py``:

  * ``python scripts/scan_ai_gateway_boundary.py``       — write baseline
  * ``python scripts/scan_ai_gateway_boundary.py --compare`` — diff vs baseline (CI gate)
  * ``python scripts/scan_ai_gateway_boundary.py --json``    — print JSON to stdout

The baseline lives at ``var/security-audit-baseline-ai-gateway-boundary.json``.
Update only when you've intentionally removed a violation — never to
silence a new one.
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
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-ai-gateway-boundary.json"
)

# The forbidden import target.
FORBIDDEN_MODULE = "services.ai_gateway"

# Allowlist: infrastructure modules that legitimately import the gateway
# directly. ALL OTHER PATHS UNDER apps/ ARE VIOLATIONS. Paths are
# repo-relative POSIX strings.
ALLOWLIST = frozenset(
    {
        # The wrapper itself.
        "services/ai_helpers.py",
        # Low-level provider tier — wraps the gateway with portal-specific
        # rules-fallback and policy guards.
        "apps/portal/ai_provider.py",
        # Explicit admin gateway surface.
        "apps/portal/views_ai_gateway.py",
        # Migration mapping bridge — uses TaskType.MIGRATION_MAPPING +
        # record_feedback hooks; this is the gateway's "real" consumer
        # for the migration_cloud app.
        "apps/migration_cloud/ai_bridge.py",
        # Provider runtime config — reads TaskType + tier metadata to
        # surface live status to portal widgets.
        "apps/platform_runtime/ai_providers.py",
        # Ops/metrics rollup command — needs `_cost_class_for_tier` to
        # bucket AIGatewayMetric rows per tier.
        "apps/siteconfig/management/commands/aggregate_ai_metrics.py",
    }
)

EXCLUDE_DIR_NAMES = {"__pycache__", "node_modules", "migrations"}
EXCLUDE_FILE_SUFFIXES = ("_test.py", "_tests.py")


def _iter_python_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
            continue
        if "tests" in rel_parts:
            # Test modules legitimately exercise the gateway directly.
            continue
        if path.name.endswith(EXCLUDE_FILE_SUFFIXES):
            continue
        yield path


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
        if rel in ALLOWLIST:
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
        "allowlist": sorted(ALLOWLIST),
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
    print(f"AI-gateway boundary scan: {len(findings)} violation(s)")
    if not findings:
        print("  (clean — every app-level caller routes through services.ai_helpers)")
        return
    for finding in findings:
        print(f"  {finding['path']}:{finding['line']}  {finding['statement']}")


def _write_baseline(findings: list[dict]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline → {BASELINE_PATH.relative_to(REPO_ROOT)}")


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
