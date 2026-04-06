#!/usr/bin/env python3
"""
Fail on unclassified non-migration cursor.execute usage.
Usage: python scripts/lint_raw_sql_usage.py [--exit-zero] [--base DIR] [--allowlist FILE]

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


def _is_cursor_factory_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "cursor"
    )


class _CursorExecuteCounter(ast.NodeVisitor):
    def __init__(self) -> None:
        self._cursor_alias_stack: list[set[str]] = [set()]
        self.count = 0

    @property
    def _cursor_aliases(self) -> set[str]:
        return self._cursor_alias_stack[-1]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_new_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_new_scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_new_scope(node)

    def _visit_new_scope(self, node: ast.AST) -> None:
        aliases = set()
        args = getattr(node, "args", None)
        if args is not None:
            for arg in (
                list(args.posonlyargs)
                + list(args.args)
                + list(args.kwonlyargs)
                + ([args.vararg] if args.vararg is not None else [])
                + ([args.kwarg] if args.kwarg is not None else [])
            ):
                if arg is None:
                    continue
                if arg.arg in {"cur", "cursor"} or arg.arg.endswith("_cursor"):
                    aliases.add(arg.arg)
        self._cursor_alias_stack.append(aliases)
        self.generic_visit(node)
        self._cursor_alias_stack.pop()

    def visit_With(self, node: ast.With) -> None:
        new_aliases = {
            item.optional_vars.id
            for item in node.items
            if isinstance(item.optional_vars, ast.Name)
            and _is_cursor_factory_call(item.context_expr)
        }
        self._cursor_alias_stack.append(self._cursor_aliases | new_aliases)
        for child in node.body:
            self.visit(child)
        self._cursor_alias_stack.pop()

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        new_aliases = {
            item.optional_vars.id
            for item in node.items
            if isinstance(item.optional_vars, ast.Name)
            and _is_cursor_factory_call(item.context_expr)
        }
        self._cursor_alias_stack.append(self._cursor_aliases | new_aliases)
        for child in node.body:
            self.visit(child)
        self._cursor_alias_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        if _is_cursor_factory_call(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._cursor_aliases.add(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if _is_cursor_factory_call(node.value) and isinstance(node.target, ast.Name):
            self._cursor_aliases.add(node.target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self._cursor_aliases
        ):
            self.count += 1
        self.generic_visit(node)


def _count_execute_calls(text: str) -> int:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text.count("cursor.execute(")

    counter = _CursorExecuteCounter()
    counter.visit(tree)
    return counter.count


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint cursor.execute usage against an allowlist."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    parser.add_argument(
        "--allowlist",
        default="scripts/allowlists/raw_sql_allowlist.json",
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
        print(f"lint_raw_sql_usage: {exc}", file=sys.stderr)
        return 1
    allowlist_path = (base / args.allowlist).resolve()
    allowlist = _load_allowlist(allowlist_path)
    counts: dict[str, int] = {}

    for path in _iter_candidate_python_files(base):
        rel = path.relative_to(base).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        count = _count_execute_calls(text)
        if count:
            counts[rel] = count

    violations: list[str] = []
    for rel, count in sorted(counts.items()):
        entry = allowlist.get(rel)
        if not entry:
            violations.append(f"Unexpected raw SQL usage in {rel} ({count} hit(s))")
            continue
        expected_count = int(entry.get("expected_count", 0))
        if count != expected_count:
            violations.append(
                f"Raw SQL count changed in {rel}: expected {expected_count}, found {count}"
            )

    for rel in sorted(set(allowlist) - set(counts)):
        expected_count = int(allowlist[rel].get("expected_count", 0))
        if expected_count:
            violations.append(f"Allowlisted raw SQL path missing from scan: {rel}")

    if violations:
        print("lint_raw_sql_usage: violations detected:\n", file=sys.stderr)
        for msg in violations:
            print(f"  {msg}", file=sys.stderr)
        return 0 if args.exit_zero else 1

    print(
        "lint_raw_sql_usage: All non-migration raw SQL usage is classified and unchanged."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
