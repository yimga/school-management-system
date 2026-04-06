#!/usr/bin/env python3
"""
Wave 4.2: Flag get_tenant_cache_prefix(None) in tenant apps.
Tenant-specific caches must not use None (public prefix); pass request or school_id.
Usage: python scripts/lint_tenant_cache_prefix.py [--base REPO_ROOT] [--exit-zero]

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

# Tenant apps where cache keys should be tenant-scoped (no None).
TENANT_APP_PREFIXES = (
    "apps/portal",
    "apps/evals",
    "apps/finance",
    "apps/people",
    "apps/communication",
    "apps/accounts",
    "apps/reports",
    "apps/analytics",
    "apps/requests",
    "apps/compliance",
)

SKIP_DIRS = {"migrations", "__pycache__", ".git", "venv", ".venv", "node_modules"}
# Files where get_tenant_cache_prefix(None) is allowed (test fixtures only).
ALLOWED_PREFIX_NONE = ("apps/evals/tests/",)

PATTERN = re.compile(r"get_tenant_cache_prefix\s*\(\s*None\s*\)")

ROOT = Path(__file__).resolve().parent.parent


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


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


def _iter_tenant_app_python_files(root: Path, app_path: Path):
    tracked = _tracked_file_relpaths(root)
    if tracked is not None:
        prefix = f"{app_path.relative_to(root).as_posix().rstrip('/')}/"
        for rel in sorted(tracked):
            if not rel.startswith(prefix) or not rel.endswith(".py"):
                continue
            py = root / Path(rel)
            if py.is_file():
                yield py
        return
    yield from app_path.rglob("*.py")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Lint: no get_tenant_cache_prefix(None) in tenant apps."
    )
    ap.add_argument(
        "--base",
        type=str,
        default=str(ROOT),
        help="Repo root (defaults to this repository root).",
    )
    ap.add_argument(
        "--exit-zero", action="store_true", help="Always exit 0 (report only)."
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"lint_tenant_cache_prefix: {exc}", file=sys.stderr)
        return 1
    apps_dir = root / "apps"
    if not apps_dir.is_dir():
        print("Apps dir not found.", file=sys.stderr)
        return 0 if args.exit_zero else 1

    hits = []
    for app_path in apps_dir.iterdir():
        if not app_path.is_dir():
            continue
        rel_prefix = f"apps/{app_path.name}"
        if rel_prefix not in [p for p in TENANT_APP_PREFIXES]:
            continue
        for py in _iter_tenant_app_python_files(root, app_path):
            rel = str(py.relative_to(root)).replace("\\", "/")
            if any(s in rel for s in SKIP_DIRS):
                continue
            if any(rel.startswith(a) for a in ALLOWED_PREFIX_NONE):
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in PATTERN.finditer(text):
                line = text[: m.start()].count("\n") + 1
                hits.append((rel, line))

    if not hits:
        print(
            "lint_tenant_cache_prefix: No get_tenant_cache_prefix(None) in tenant apps."
        )
        return 0
    print(
        "lint_tenant_cache_prefix: get_tenant_cache_prefix(None) in tenant apps (use request or school_id):",
        file=sys.stderr,
    )
    for rel, line in hits:
        print(f"  {rel}:{line}", file=sys.stderr)
    return 0 if args.exit_zero else 1


if __name__ == "__main__":
    raise SystemExit(main(None))
