#!/usr/bin/env python3
"""
Fail if print( appears in apps/**/*.py outside tests/ or management/commands/.
Use in CI to enforce structured logging in application paths.
Exit 0 if none found; 1 and list files if found.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

# Allowlist: test and management command files may use print for dev/debug.
ALLOWLIST_DIRS = ("tests", "management", "migrations")
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


def _iter_app_python_files(root: Path):
    tracked = _tracked_file_relpaths(root)
    if tracked is not None:
        for rel in sorted(tracked):
            if not rel.startswith("apps/") or not rel.endswith(".py"):
                continue
            py = root / Path(rel)
            if py.is_file():
                yield py
        return
    apps = root / "apps"
    yield from apps.rglob("*.py")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail if print( appears in apps/**/*.py outside tests/ or management/commands/."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"lint_no_print_in_apps: {exc}", file=sys.stderr)
        return 1
    found = []
    for py in _iter_app_python_files(root):
        rel = py.relative_to(root)
        parts = rel.parts
        if "apps" not in parts:
            continue
        # Allow tests, management commands, migrations
        if any(d in parts for d in ALLOWLIST_DIRS):
            continue
        try:
            lines = py.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if (
                stripped.startswith("#")
                or stripped.startswith('"""')
                or stripped.startswith("'''")
            ):
                continue
            if re.search(r"\bprint\s*\(", line):
                found.append(f"{rel}:{i}")
                break
    if not found:
        print(
            "OK: No print() in application code (apps/ excluding tests, management, migrations)."
        )
        return 0
    print(
        "ERROR: print() found in application code. Use logging.getLogger(__name__) instead.",
        file=sys.stderr,
    )
    for f in sorted(found):
        print(f"  {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(None))
