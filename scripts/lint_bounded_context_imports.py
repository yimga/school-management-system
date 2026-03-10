#!/usr/bin/env python3
"""
Bounded context import check: tenant-facing apps must not import control-plane models.
Matches apps.tenancy.tests.test_control_plane_boundary. Run in CI to fail on violations.
Usage: python scripts/lint_bounded_context_imports.py [--strict] [--exit-zero]
With BOUNDED_CONTEXT_STRICT=1 or --strict: exit 1 on any violation. Otherwise exit 0 (report only).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Tenant-facing app labels (must not import control-plane ORM directly).
TENANT_APPS = (
    "portal",
    "student360",
    "academics",
    "people",
    "finance",
    "evals",
    "reports",
    "communication",
    "dashboard",
    "payroll",
    "requests",
    "api",
    "observability",
    "analytics",
)

EXCLUDE_DIRS = ("migrations", "management", "tests", "__pycache__")
FORBIDDEN_PATTERNS = (
    (re.compile(r"from\s+apps\.customers\.models\s+import"), "apps.customers.models"),
    (re.compile(r"from\s+apps\.marketplace\.models\s+import"), "apps.marketplace.models"),
    (re.compile(r"from\s+apps\.policies\.models\s+import"), "apps.policies.models"),
)


def find_apps_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    root = script_dir.parent
    apps_dir = root / "apps"
    if apps_dir.is_dir():
        return root
    raise SystemExit("Cannot find repo root (apps/ not found).")


def collect_py_files(app_path: Path) -> list[Path]:
    files = []
    for root, _dirs, filenames in os.walk(app_path):
        rel = Path(root)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        for name in filenames:
            if name.endswith(".py") and not name.startswith("__"):
                files.append(Path(root) / name)
    return files


def check_file(path: Path) -> list[tuple[str, str]]:
    violations = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, label in FORBIDDEN_PATTERNS:
                if pattern.search(stripped):
                    violations.append((line.strip(), label))
                    break
    except Exception:
        pass
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint bounded context imports (tenant vs control-plane).")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any violation (CI gate).")
    parser.add_argument("--exit-zero", action="store_true", help="Always exit 0 (report only).")
    args = parser.parse_args()
    strict = args.strict or os.environ.get("BOUNDED_CONTEXT_STRICT") == "1"
    if args.exit_zero:
        strict = False

    root = find_apps_root()
    base = root / "apps"
    all_violations = []
    for app_label in TENANT_APPS:
        app_path = base / app_label
        if not app_path.is_dir():
            continue
        for py_path in collect_py_files(app_path):
            rel = py_path.relative_to(root)
            for line, label in check_file(py_path):
                all_violations.append((str(rel), label, line))

    if all_violations:
        print("Bounded context violations (tenant apps must not import control-plane models):", file=sys.stderr)
        for path, label, line in all_violations:
            print(f"  {path}: {label}", file=sys.stderr)
            print(f"    {line}", file=sys.stderr)
        if strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
