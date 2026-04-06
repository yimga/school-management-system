#!/usr/bin/env python3
"""
Block provider secret exposure in client assets and tracked env/config files.

Checks:
- secret identifiers must not appear in client-rendered templates or frontend assets
- context processors must not expose provider secret keys to templates
- provider secret identifiers must not appear broadly in server code (confine to provider/gateway modules)
- tracked env files must not contain non-empty provider secret assignments

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

CLIENT_DIRS = ("templates", "frontend", "static")
SERVER_DIRS = ("apps", "services")
SECRET_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "MISTRAL_API_KEY",
)
SECRET_NAME_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in SECRET_NAMES) + r")\b"
)
ENV_ASSIGNMENT_PATTERN = re.compile(
    r"^\s*(" + "|".join(re.escape(name) for name in SECRET_NAMES) + r")\s*=\s*(.+?)\s*$"
)
PLACEHOLDER_TOKENS = (
    "",
    "changeme",
    "replace_me",
    "your_",
    "<",
    "example",
    "placeholder",
)
SKIP_DIRS = {"migrations", "tests", "__pycache__", ".venv", "venv", "node_modules"}
ALLOWED_SERVER_SECRET_REF_PREFIXES: tuple[str, ...] = ()


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


def _iter_tracked_files(
    root: Path,
    *,
    prefixes: tuple[str, ...] = (),
    suffixes: tuple[str, ...] = (),
    name: str | None = None,
    skip_parts: set[str] | None = None,
):
    tracked = _tracked_file_relpaths(root)
    if tracked is None:
        return None
    matched: list[Path] = []
    for rel in sorted(tracked):
        path = root / Path(rel)
        if not path.is_file():
            continue
        if prefixes and not rel.startswith(prefixes):
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        if name is not None and path.name != name:
            continue
        if skip_parts and any(part in skip_parts for part in path.parts):
            continue
        matched.append(path)
    return matched


def _tracked_root_env_files(root: Path) -> list[Path]:
    tracked = _iter_tracked_files(root, suffixes=(".env", ".yaml", ".yml"))
    if tracked is None:
        return []
    files: list[Path] = []
    for path in tracked:
        if path.name.startswith(".env") or path.suffix in {".env", ".yaml", ".yml"}:
            files.append(path)
    return files


def _client_files(root: Path) -> list[Path]:
    tracked = _iter_tracked_files(
        root,
        prefixes=tuple(f"{dirname}/" for dirname in CLIENT_DIRS),
        suffixes=(".html", ".js", ".jsx", ".ts", ".tsx"),
    )
    if tracked is not None:
        return tracked
    files: list[Path] = []
    for dirname in CLIENT_DIRS:
        base = root / dirname
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix.lower() not in {".html", ".js", ".jsx", ".ts", ".tsx"}:
                continue
            files.append(path)
    return files


def _context_processor_files(root: Path) -> list[Path]:
    tracked = _iter_tracked_files(root, prefixes=("apps/",), name="context_processors.py")
    if tracked is not None:
        return tracked
    files: list[Path] = []
    apps_dir = root / "apps"
    if not apps_dir.is_dir():
        return files
    for path in apps_dir.rglob("context_processors.py"):
        files.append(path)
    return files


def _server_code_files(root: Path) -> list[Path]:
    tracked = _iter_tracked_files(
        root,
        prefixes=tuple(f"{dirname}/" for dirname in SERVER_DIRS),
        suffixes=(".py",),
        skip_parts=SKIP_DIRS,
    )
    if tracked is not None:
        return tracked
    files: list[Path] = []
    for dirname in SERVER_DIRS:
        base = root / dirname
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            files.append(path)
    return files


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Block provider secret exposure in client assets and tracked env/config files."
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
        print(f"lint_secret_exposure: {exc}", file=sys.stderr)
        return 1

    violations: list[str] = []

    for path in _client_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if SECRET_NAME_PATTERN.search(line):
                rel = path.relative_to(root).as_posix()
                violations.append(
                    f"{rel}:{line_no} references a provider secret name in client-rendered code"
                )

    for path in _context_processor_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if SECRET_NAME_PATTERN.search(line):
                rel = path.relative_to(root).as_posix()
                violations.append(
                    f"{rel}:{line_no} references a provider secret name in a context processor"
                )

    for path in _server_code_files(root):
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(prefix) for prefix in ALLOWED_SERVER_SECRET_REF_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if SECRET_NAME_PATTERN.search(line):
                violations.append(
                    f"{rel}:{line_no} references a provider secret name outside allowed server modules"
                )

    for path in _tracked_root_env_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(root).as_posix()
        for line_no, line in enumerate(text.splitlines(), start=1):
            match = ENV_ASSIGNMENT_PATTERN.match(line)
            if not match:
                continue
            value = match.group(2).strip().strip("'\"")
            lowered = value.lower()
            if any(token and token in lowered for token in PLACEHOLDER_TOKENS[3:]):
                continue
            if lowered in PLACEHOLDER_TOKENS[:3] or not value:
                continue
            violations.append(
                f"{rel}:{line_no} contains a non-placeholder provider secret assignment"
            )

    if violations:
        print("lint_secret_exposure: violations detected:\n", file=sys.stderr)
        for violation in sorted(violations):
            print(f"  {violation}", file=sys.stderr)
        return 1

    print(
        "lint_secret_exposure: no client-side or tracked-config provider secret exposure found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
