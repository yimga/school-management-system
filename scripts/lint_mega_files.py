#!/usr/bin/env python3
"""
Plan A4: Fail CI when any Python file in apps/ exceeds max line count (mega-file guardrail).

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
Usage: ``python scripts/lint_mega_files.py [--max-lines N] [--exit-zero] [--base PATH]``
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"migrations", "__pycache__", "venv", ".venv", "node_modules"}
DEFAULT_MAX_LINES = 4500  # 2.1 splits done; lower to 3500 once siteconfig/models + marketing_views decomposed


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


def _iter_app_python_files(base: Path):
    tracked = _tracked_file_relpaths(base)
    if tracked is not None:
        for rel in sorted(tracked):
            if not rel.startswith("apps/") or not rel.endswith(".py"):
                continue
            py = base / Path(rel)
            if not py.is_file():
                continue
            if any(part in SKIP_DIRS for part in py.parts):
                continue
            yield py
        return
    apps_dir = base / "apps"
    yield from apps_dir.rglob("*.py")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Fail if any app .py file exceeds max lines."
    )
    ap.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help=f"Max lines per file (default {DEFAULT_MAX_LINES})",
    )
    ap.add_argument(
        "--exit-zero", action="store_true", help="Always exit 0 (report only)."
    )
    ap.add_argument(
        "--base",
        default=str(ROOT),
        help="Base directory (defaults to this repository root).",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base = _resolve_base(args.base)
    except ValueError as exc:
        print(f"lint_mega_files: {exc}", file=sys.stderr)
        return 1

    apps_dir = base / "apps"
    if not apps_dir.is_dir():
        print("No apps/ directory.", file=sys.stderr)
        return 0

    hits: list[tuple[str, int]] = []
    for py in _iter_app_python_files(base):
        try:
            line_count = sum(1 for _ in py.open(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if line_count > args.max_lines:
            rel = py.relative_to(base)
            hits.append((str(rel).replace("\\", "/"), line_count))

    if not hits:
        print(f"lint_mega_files: No file in apps/ exceeds {args.max_lines} lines.")
        return 0
    print(f"lint_mega_files: Files exceeding {args.max_lines} lines (plan A4 / §15):\n")
    for path, count in sorted(hits, key=lambda x: -x[1]):
        print(f"  {path}: {count} lines")
    print(
        f"\nTotal: {len(hits)} file(s). Decompose by domain (see NEXT_PHASE_BACKLOG A2/B1)."
    )
    return 0 if args.exit_zero else 1


if __name__ == "__main__":
    raise SystemExit(main(None))
