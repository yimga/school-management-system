#!/usr/bin/env python3
"""
Fail on unclassified AllowAny usage.
Usage: python scripts/lint_allow_any_usage.py [--exit-zero] [--base DIR] [--allowlist FILE]

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "migrations", "tests"}
REQUIRED_METADATA_FIELDS = (
    "owner",
    "verdict",
    "auth_model",
    "data_exposure",
    "rate_limiting",
    "audit_logging",
    "notes",
)


def _load_allowlist(path: Path) -> dict[str, dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("files", {})


@lru_cache(maxsize=None)
def _tracked_file_relpaths(root: Path) -> frozenset[str] | None:
    """Prefer tracked files so local scratch trees do not create false positives."""
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
            cwd=str(root),
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    relpaths: set[str] = set()
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            relpaths.add(Path(raw.decode("utf-8")).as_posix())
        except UnicodeDecodeError:
            continue
    return frozenset(relpaths)


def _iter_candidate_python_files(base: Path):
    tracked = _tracked_file_relpaths(base)
    if tracked is not None:
        scan_prefixes = ("apps/", "config/")
        for rel in sorted(tracked):
            if not rel.startswith(scan_prefixes):
                continue
            path = base / Path(rel)
            if not path.is_file() or path.suffix.lower() != ".py":
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            yield path
        return
    for root_name in ("apps", "config"):
        root = base / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            yield path


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _count_allow_any(text: str, rel: str) -> int:
    tree = ast.parse(text, filename=rel)
    count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "rest_framework.permissions"
        ):
            count += sum(1 for alias in node.names if alias.name == "AllowAny")
        elif isinstance(node, ast.Name) and node.id == "AllowAny":
            count += 1
    return count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint AllowAny usage against an allowlist."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    parser.add_argument(
        "--allowlist",
        default="scripts/allowlists/allow_any_allowlist.json",
        help="Allowlist JSON path",
    )
    parser.add_argument(
        "--exit-zero", action="store_true", help="Always exit 0 (report only)."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        base = _resolve_base(args.base)
    except ValueError as exc:
        print(f"lint_allow_any_usage: {exc}", file=sys.stderr)
        return 1
    allowlist_path = (base / args.allowlist).resolve()
    allowlist = _load_allowlist(allowlist_path)
    counts: dict[str, int] = {}

    for path in _iter_candidate_python_files(base):
        rel = path.relative_to(base).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        count = _count_allow_any(text, rel)
        if count:
            counts[rel] = count

    violations: list[str] = []
    for rel, count in sorted(counts.items()):
        entry = allowlist.get(rel)
        if not entry:
            violations.append(f"Unexpected AllowAny usage in {rel} ({count} hit(s))")
            continue
        expected_count = int(entry.get("expected_count", 0))
        if count != expected_count:
            violations.append(
                f"AllowAny count changed in {rel}: expected {expected_count}, found {count}"
            )
        missing_metadata = [
            field
            for field in REQUIRED_METADATA_FIELDS
            if not str(entry.get(field, "")).strip()
        ]
        if missing_metadata:
            violations.append(
                f"AllowAny allowlist entry for {rel} is missing metadata: {', '.join(missing_metadata)}"
            )

    for rel in sorted(set(allowlist) - set(counts)):
        expected_count = int(allowlist[rel].get("expected_count", 0))
        if expected_count:
            violations.append(f"Allowlisted AllowAny path missing from scan: {rel}")

    if violations:
        print("lint_allow_any_usage: violations detected:\n", file=sys.stderr)
        for msg in violations:
            print(f"  {msg}", file=sys.stderr)
        return 0 if args.exit_zero else 1

    print("lint_allow_any_usage: All AllowAny usage is classified and unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
