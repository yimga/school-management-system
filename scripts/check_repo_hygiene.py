#!/usr/bin/env python3
"""
Repo hygiene: fail CI on conflict markers, backup files, and debug debris.
Usage: python scripts/check_repo_hygiene.py [--exit-zero] [--base DIR]

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "htmlcov",
    ".pytest_cache",
    "media",
    "static",
    "backups",
    "staticfiles",
}
# Only scan likely text files for conflict markers (skip binaries).
TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".sh",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".sql",
    ".txt",
    ".toml",
    ".ini",
    ".cfg",
}
BACKUP_GLOB = ("*.bak", "*.orig", "*.tmp")
# Full-line merge conflict markers (exact match per line)
CONFLICT_LINE_EXACT = ("<<<<<<<", "=======", ">>>>>>>")
# Or line starts with branch marker (<<<<<<< branch, >>>>>>> branch)
CONFLICT_LINE_STARTS = ("<<<<<<< ", ">>>>>>> ")


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
            cwd=root,
            check=False,
            capture_output=True,
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


def _iter_conflict_candidate_files(base: Path):
    tracked = _tracked_file_relpaths(base)
    if tracked is not None:
        for rel in sorted(tracked):
            path = base / Path(rel)
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS or path.name.startswith("."):
                continue
            yield path
        return
    for path in base.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS or path.name.startswith("."):
            continue
        if not path.is_file():
            continue
        yield path


def _iter_backup_files(base: Path):
    tracked = _tracked_file_relpaths(base)
    if tracked is not None:
        for rel in sorted(tracked):
            path = base / Path(rel)
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if any(path.match(pattern) for pattern in BACKUP_GLOB):
                yield path
        return
    for pattern in BACKUP_GLOB:
        for path in base.rglob(pattern):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file():
                yield path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Check repo for conflict markers and backup/debug files."
    )
    ap.add_argument(
        "--exit-zero", action="store_true", help="Always exit 0 (report only)."
    )
    ap.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base = _resolve_base(args.base)
    except ValueError as exc:
        print(f"check_repo_hygiene: {exc}", file=sys.stderr)
        return 1

    errors = []

    # Conflict markers in text files (only likely text extensions)
    for path in _iter_conflict_candidate_files(base):
        try:
            text = path.read_bytes()
            if b"\x00" in text[:8192]:
                continue
            text_str = text[:50000].decode("utf-8", errors="replace")
            for line in text_str.splitlines():
                s = line.strip()
                if s in CONFLICT_LINE_EXACT:
                    errors.append(f"Conflict marker '{s}' in {path.relative_to(base)}")
                    break
                if any(line.startswith(prefix) for prefix in CONFLICT_LINE_STARTS):
                    errors.append(f"Conflict marker in {path.relative_to(base)}")
                    break
        except OSError:
            continue

    # Backup / debris files
    for path in _iter_backup_files(base):
        errors.append(f"Backup/debris file: {path.relative_to(base)}")

    if errors:
        print("Repo hygiene violations:\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 0 if args.exit_zero else 1
    print("check_repo_hygiene: No conflict markers or backup files found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
