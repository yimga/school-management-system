#!/usr/bin/env python3
"""
Bounded context import check: tenant-facing apps must not import control-plane models.
Matches apps.tenancy.tests.test_control_plane_boundary. Run in CI to fail on violations.
Usage: python scripts/lint_bounded_context_imports.py [--strict] [--exit-zero]
With BOUNDED_CONTEXT_STRICT=1 or --strict: exit 1 on any violation. Otherwise exit 0 (report only).

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

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
    (
        re.compile(r"from\s+apps\.marketplace\.models\s+import"),
        "apps.marketplace.models",
    ),
    (re.compile(r"from\s+apps\.policies\.models\s+import"), "apps.policies.models"),
)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def find_apps_root(base: str = ".") -> Path:
    root = _resolve_base(base)
    apps_dir = root / "apps"
    if apps_dir.is_dir():
        return root
    raise SystemExit("Cannot find repo root (apps/ not found).")


@lru_cache(maxsize=None)
def _tracked_file_relpaths(root: Path) -> frozenset[str] | None:
    """Prefer tracked files so local scratch trees do not create false positives."""
    if not (root / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
            cwd=str(root),
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    relpaths: set[str] = set()
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            relpaths.add(Path(raw.decode("utf-8")).as_posix())
        except UnicodeDecodeError:
            continue
    return frozenset(relpaths)


def collect_py_files(app_path: Path) -> list[Path]:
    repo_root = app_path.parents[1]
    tracked = _tracked_file_relpaths(repo_root)
    if tracked is not None:
        prefix = f"{app_path.relative_to(repo_root).as_posix().rstrip('/')}/"
        files: list[Path] = []
        for rel in sorted(tracked):
            if not rel.startswith(prefix) or not rel.endswith(".py"):
                continue
            path = repo_root / Path(rel)
            if not path.is_file():
                continue
            if path.name.startswith("__"):
                continue
            if any(part in EXCLUDE_DIRS for part in path.parts):
                continue
            files.append(path)
        return files
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
    except OSError:
        return violations
    return violations


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint bounded context imports (tenant vs control-plane)."
    )
    parser.add_argument(
        "--strict", action="store_true", help="Exit 1 on any violation (CI gate)."
    )
    parser.add_argument(
        "--exit-zero", action="store_true", help="Always exit 0 (report only)."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    strict = args.strict or os.environ.get("BOUNDED_CONTEXT_STRICT") == "1"
    if args.exit_zero:
        strict = False

    try:
        root = find_apps_root(args.base)
    except ValueError as exc:
        print(f"lint_bounded_context_imports: {exc}", file=sys.stderr)
        return 1
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
        print(
            "Bounded context violations (tenant apps must not import control-plane models):",
            file=sys.stderr,
        )
        for path, label, line in all_violations:
            print(f"  {path}: {label}", file=sys.stderr)
            print(f"    {line}", file=sys.stderr)
        if strict:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
