#!/usr/bin/env python3
"""
Fail fast on high-risk secret patterns in committed source (complements lint_secret_exposure.py).

Scans text files under apps/, config/, services/ — excludes migrations, __pycache__, static vendor.
Exit 0 = no matches; exit 1 = findings.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ("apps", "config", "services")
SKIP_PARTS = frozenset(
    {
        "migrations",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
    }
)
# Patterns that strongly suggest committed credentials (not exhaustive).
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "AWS access key (20 chars)",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
    (
        "Stripe live secret",
        re.compile(r"\bsk_live_[0-9a-zA-Z]{20,}\b"),
    ),
    (
        "GitHub classic PAT (ghp_)",
        re.compile(r"\bghp_[0-9a-zA-Z]{30,}\b"),
    ),
    (
        "GitHub fine-grained PAT (github_pat_)",
        re.compile(r"\bgithub_pat_[0-9a-zA-Z_]{20,}\b"),
    ),
]


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


def _iter_files(root: Path) -> list[Path]:
    tracked = _tracked_file_relpaths(root)
    if tracked is not None:
        out: list[Path] = []
        scan_prefixes = tuple(f"{name}/" for name in SCAN_ROOTS)
        allowed_suffixes = {".py", ".html", ".js", ".ts", ".tsx", ".yml", ".yaml", ".json", ".md", ".sh"}
        for rel in sorted(tracked):
            if not rel.startswith(scan_prefixes):
                continue
            p = root / Path(rel)
            if not p.is_file():
                continue
            parts = set(p.parts)
            if parts & SKIP_PARTS:
                continue
            if p.suffix.lower() not in allowed_suffixes:
                continue
            out.append(p)
        return out
    out: list[Path] = []
    for name in SCAN_ROOTS:
        base = root / name
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            parts = set(p.parts)
            if parts & SKIP_PARTS:
                continue
            if p.suffix.lower() not in {".py", ".html", ".js", ".ts", ".tsx", ".yml", ".yaml", ".json", ".md", ".sh"}:
                continue
            out.append(p)
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan repo text files for high-risk secret patterns."
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
        print(f"scan_repo_secrets: {exc}", file=sys.stderr)
        return 1

    bad: list[str] = []
    for path in _iter_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for label, rx in PATTERNS:
            if rx.search(text):
                # Allow obvious placeholders in docs/tests
                if "/tests/" in str(path).replace("\\", "/") and "AKIA" in label:
                    if "EXAMPLE" in text or "placeholder" in text.lower():
                        continue
                bad.append(f"{path.relative_to(root)}: possible {label}")

    if bad:
        print("scan_repo_secrets: potential secret-like strings found:", file=sys.stderr)
        for line in bad[:50]:
            print(f"  {line}", file=sys.stderr)
        if len(bad) > 50:
            print(f"  ... and {len(bad) - 50} more", file=sys.stderr)
        return 1
    print("scan_repo_secrets: OK (no high-risk patterns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
