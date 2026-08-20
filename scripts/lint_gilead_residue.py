#!/usr/bin/env python3
"""
Block runtime-visible Gilead residue in the active platform surface.

Historical references inside migrations, archived docs, and tests are allowed
until the data migration history is retired. Runtime-visible defaults, fixtures,
deployment config, and user-facing surfaces are not.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Founding-school-SPECIFIC residue with no legitimate generic use. Deliberately does
# NOT include bare "Cameroon"/"Buea" — Cameroon is a fully-supported country across the
# region-pack/exam-board infra, so banning it would flag legitimate localization code.
# "Small Soppo" is the founding school's specific neighbourhood (only ever a leaked default).
PATTERN = re.compile(r"gilead|small\s+soppo", re.IGNORECASE)
SCAN_ROOT_NAMES = ("apps", "services", "fixtures", "templates", "config")
SCAN_FILE_NAMES = ("render.yaml", "QUICK_START.md")
SKIP_PARTS = {"migrations", "tests", "__pycache__", "docs", "tmp", "artifacts"}


def _safe_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


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


def _mask_python_noncode(source: str) -> str:
    """Blank `#` comments and docstrings; keep every other string literal.

    Returns text of identical shape (non-newline chars become spaces) so the
    reported line numbers still match the file on disk. On any tokenize/parse
    error the source is returned unchanged -- this gate must never go quiet
    because a file was hard to parse.
    """
    try:
        lines = source.splitlines(keepends=True)
        grid = [list(line) for line in lines]

        def _blank(lineno: int, col_start: int, end_lineno: int, col_end: int) -> None:
            for ln in range(lineno, end_lineno + 1):
                if not (1 <= ln <= len(grid)):
                    continue
                row = grid[ln - 1]
                start = col_start if ln == lineno else 0
                stop = col_end if ln == end_lineno else len(row)
                for c in range(start, min(stop, len(row))):
                    if row[c] != "\n":
                        row[c] = " "

        # 1) comments
        import io
        import tokenize

        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                _blank(tok.start[0], tok.start[1], tok.end[0], tok.end[1])

        # 2) docstrings (module / class / function) -- NOT other strings
        import ast

        tree = ast.parse(source)
        targets = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        for node in ast.walk(tree):
            if not isinstance(node, targets):
                continue
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                s = first.value
                _blank(s.lineno, s.col_offset, s.end_lineno, s.end_col_offset)

        return "".join("".join(row) for row in grid)
    except (SyntaxError, tokenize.TokenError, ValueError, IndentationError):
        return source


def _path_skipped(path: Path, root: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return True
    # CLI-only; not user-facing HTTP/runtime surfaces (lint targets templates, APIs, config).
    rel = path.relative_to(root).as_posix()
    if "management/commands/" in rel:
        return True
    return False


def _iter_candidate_files(root: Path):
    tracked = _tracked_file_relpaths(root)
    if tracked is not None:
        scan_prefixes = tuple(f"{name}/" for name in SCAN_ROOT_NAMES)
        seen: set[Path] = set()
        for rel in sorted(tracked):
            if rel not in SCAN_FILE_NAMES and not rel.startswith(scan_prefixes):
                continue
            path = root / Path(rel)
            if not path.is_file():
                continue
            if _path_skipped(path, root):
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path
        return
    for name in SCAN_ROOT_NAMES:
        base = root / name
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if _path_skipped(path, root):
                continue
            yield path
    for name in SCAN_FILE_NAMES:
        path = root / name
        if path.exists():
            yield path


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Block runtime-visible Gilead residue in the active platform surface."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to scan (defaults to current repo root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"lint_gilead_residue: {exc}", file=sys.stderr)
        return 1
    violations: list[str] = []
    for path in sorted(set(_iter_candidate_files(root))):
        _text = _safe_text(path)
        if path.suffix == ".py":
            _text = _mask_python_noncode(_text)
        for line_no, line in enumerate(_text.splitlines(), start=1):
            if PATTERN.search(line):
                rel = path.relative_to(root).as_posix()
                violations.append(f"{rel}:{line_no}: {line.strip()}")
    if violations:
        print(
            "lint_gilead_residue: runtime-visible Gilead residue detected:\n",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    print("lint_gilead_residue: no runtime-visible Gilead residue found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
