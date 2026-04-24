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
from datetime import date
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "migrations", "tests"}

# Allowlist `files[path]` objects only carry these keys (prevents typos like `expeted_count`).
ALLOWLIST_ENTRY_KEYS = frozenset({"expected_count", "reason", "last_reviewed"})


def _load_allowlist(path: Path) -> dict[str, dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("files", {})


def _load_allowlist_document(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _validate_allowlist_metadata(document: dict[str, object]) -> list[str]:
    errors: list[str] = []
    today = date.today()


    manifest_last_reviewed = document.get("manifest_last_reviewed")
    if manifest_last_reviewed is not None and not _is_iso_date(manifest_last_reviewed):
        errors.append(
            "Invalid allowlist manifest_last_reviewed (must be YYYY-MM-DD): "
            f"{manifest_last_reviewed!r}"
        )

    if manifest_last_reviewed is not None and _is_iso_date(manifest_last_reviewed):
        if date.fromisoformat(manifest_last_reviewed) > today:
            errors.append(
                "Invalid allowlist manifest_last_reviewed (must not be in the future): "
                f"{manifest_last_reviewed!r}"
            )

    raw_files = document.get("files", {})
    if raw_files is None:
        raw_files = {}
    if not isinstance(raw_files, dict):
        errors.append(
            "Invalid allowlist files (must be an object): "
            f"{type(raw_files).__name__}"
        )
        return errors

    for rel, entry in sorted(raw_files.items()):
        if not isinstance(entry, dict):
            continue
        last_reviewed = entry.get("last_reviewed")
        if last_reviewed is not None and not _is_iso_date(last_reviewed):
            errors.append(
                f"Invalid allowlist last_reviewed for {rel} (must be YYYY-MM-DD): {last_reviewed!r}"
            )

        if last_reviewed is not None and _is_iso_date(last_reviewed):
            if date.fromisoformat(last_reviewed) > today:
                errors.append(
                    f"Invalid allowlist last_reviewed for {rel} (must not be in the future): {last_reviewed!r}"
                )

    any_positive = False
    for _rel, entry in sorted(raw_files.items()):
        if not isinstance(entry, dict):
            continue
        ec = entry.get("expected_count", 0)
        if isinstance(ec, int) and ec > 0:
            any_positive = True
            break
    if any_positive and manifest_last_reviewed is None:
        errors.append(
            "Invalid allowlist: manifest_last_reviewed is required when any file has expected_count > 0"
        )

    return errors



def _validate_allowlist_relpaths(relpaths: list[str]) -> list[str]:
    errors: list[str] = []
    for rel in relpaths:
        if not isinstance(rel, str) or not rel:
            errors.append(f"Invalid allowlist path key: {rel!r}")
            continue
        if "\\" in rel:
            errors.append(f"Invalid allowlist path (must use /): {rel}")
        if rel.startswith("/") or rel.startswith("\\"):
            errors.append(f"Invalid allowlist path (must be relative): {rel}")
        if not rel.endswith(".py"):
            errors.append(f"Invalid allowlist path (must be a .py file): {rel}")
        parts = [p for p in rel.split("/") if p not in {"", "."}]
        if any(p == ".." for p in parts):
            errors.append(f"Invalid allowlist path (must not contain ..): {rel}")
        if not rel.startswith(("apps/", "config/")):
            errors.append(
                f"Invalid allowlist path (must start with apps/ or config/): {rel}"
            )
        if rel.endswith("/") or rel.endswith("\\"):
            errors.append(f"Invalid allowlist path (must be a file): {rel}")
    return errors


def _validate_allowlist_entries(allowlist: dict[str, dict[str, object]]) -> list[str]:
    errors: list[str] = []
    for rel, entry in sorted(allowlist.items()):
        if entry is None:
            errors.append(f"Invalid allowlist entry for {rel}: must be an object")
            continue
        if not isinstance(entry, dict):
            errors.append(
                f"Invalid allowlist entry for {rel}: must be an object, got {type(entry).__name__}"
            )
            continue
        for key in entry:
            if key not in ALLOWLIST_ENTRY_KEYS:
                errors.append(
                    f"Invalid allowlist entry for {rel}: unknown key {key!r} "
                    f"(allowed: {sorted(ALLOWLIST_ENTRY_KEYS)})"
                )
        if "expected_count" not in entry:
            errors.append(f"Invalid allowlist entry for {rel}: missing expected_count")
            continue
        raw_expected = entry.get("expected_count", 0)
        if raw_expected is None:
            raw_expected = 0
        if not isinstance(raw_expected, int):
            errors.append(
                f"Invalid expected_count for {rel}: must be int, got {type(raw_expected).__name__}"
            )
            continue
        if raw_expected < 0:
            errors.append(f"Invalid expected_count for {rel}: must be >= 0")
            continue

        if raw_expected > 0:
            reason = entry.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(
                    f"Invalid allowlist entry for {rel}: reason is required when expected_count > 0"
                )
            if "last_reviewed" not in entry or entry.get("last_reviewed") is None:
                errors.append(
                    f"Invalid allowlist entry for {rel}: last_reviewed is required when expected_count > 0"
                )
        else:
            reason = entry.get("reason")
            if reason is not None and (
                not isinstance(reason, str) or not reason.strip()
            ):
                errors.append(f"Invalid reason for {rel}: must be non-empty string")
    return errors


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
    try:
        allowlist_path.relative_to(base)
    except ValueError:
        print(
            f"lint_raw_sql_usage: allowlist path must be within --base (got {args.allowlist})",
            file=sys.stderr,
        )
        return 1
    try:
        document = _load_allowlist_document(allowlist_path)
        allowlist = document.get("files", {})
    except FileNotFoundError:
        print(
            f"lint_raw_sql_usage: allowlist file not found: {args.allowlist}",
            file=sys.stderr,
        )
        return 1
    except json.JSONDecodeError as exc:
        print(
            f"lint_raw_sql_usage: allowlist JSON invalid at {args.allowlist}: {exc}",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(
            f"lint_raw_sql_usage: allowlist read failed at {args.allowlist}: {exc}",
            file=sys.stderr,
        )
        return 1
    allowlist_errors = _validate_allowlist_relpaths(sorted(allowlist))
    allowlist_errors.extend(_validate_allowlist_metadata(document))
    allowlist_errors.extend(_validate_allowlist_entries(allowlist))
    if allowlist_errors:
        print(
            "lint_raw_sql_usage: invalid allowlist paths detected:\n",
            file=sys.stderr,
        )
        for msg in allowlist_errors:
            print(f"  {msg}", file=sys.stderr)
        return 1
    candidate_paths = list(_iter_candidate_python_files(base))
    scanned_relpaths = {p.relative_to(base).as_posix() for p in candidate_paths}

    counts: dict[str, int] = {}
    for path in candidate_paths:
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

    for rel in sorted(set(allowlist) - scanned_relpaths):
        expected_count = int(allowlist[rel].get("expected_count", 0))
        if expected_count:
            violations.append(f"Allowlisted raw SQL path missing from scan: {rel}")

    for rel in sorted(set(allowlist) & scanned_relpaths - set(counts)):
        expected_count = int(allowlist[rel].get("expected_count", 0))
        if expected_count:
            violations.append(
                f"Raw SQL count changed in {rel}: expected {expected_count}, found 0"
            )

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
