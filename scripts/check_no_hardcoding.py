#!/usr/bin/env python3
"""
No-hardcoding enforcement (RunMyCampus architecture).
Flags likely tenant/country/region hardcoding in app code. Run in CI or pre-push.
Excludes: control plane, migrations, tests (optional), and allowlisted paths.
Usage: python scripts/check_no_hardcoding.py [--allow-tests] [--exit-zero] [--base REPO_ROOT]

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

# Patterns that suggest hardcoded tenant/country/region logic (app code should use policy).
PATTERNS = [
    (re.compile(r'\bcountry\s*==\s*["\']'), 'country == "..." (use policy/tenant_ctx)'),
    (re.compile(r"\btenant\.country\s*=="), "tenant.country == (use policy)"),
    (re.compile(r'\bregion\s*==\s*["\']'), 'region == "..." (use policy)'),
    (re.compile(r'\bcountry_code\s*==\s*["\']'), 'country_code == "..." (use policy)'),
    (
        re.compile(r'\bin\s*\[\s*["\'](?:CM|FR|US|NG|KE|GB|AE)\s*["\']'),
        'in ["CM", ...] country list (use policy/registry)',
    ),
    (re.compile(r"if\s+.*\.country\s*=="), "if ... .country == (use policy)"),
]

# Paths to skip (control plane, migrations, seed data, docs, this script).
SKIP_DIRS = {
    "migrations",
    "management/commands",  # some commands intentionally use country for seed
    "node_modules",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "scripts",  # this script and other tooling
    "docs",
    "config/settings",  # env-specific, not tenant logic
}
SKIP_FILES = {
    "check_no_hardcoding.py",
    "currency_seed.py",  # registry seed by country code
    "region_seed.py",
    "locale_seed.py",
    # Regional payment/translation fallbacks; TODO: move to policy/registry
    "payment_processors.py",
    "translations.py",
}


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


def _iter_python_files(base: Path):
    tracked = _tracked_file_relpaths(base)
    if tracked is not None:
        for rel in sorted(tracked):
            if not rel.endswith(".py"):
                continue
            py = base / Path(rel)
            if not py.is_file():
                continue
            yield py
        return
    yield from base.rglob("*.py")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Flag tenant/country/region hardcoding in app code."
    )
    ap.add_argument(
        "--allow-tests", action="store_true", help="Do not flag test files."
    )
    ap.add_argument(
        "--exit-zero", action="store_true", help="Always exit 0 (report only)."
    )
    ap.add_argument(
        "--base",
        default=str(ROOT),
        help="Base directory to scan (defaults to this repository root).",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base = _resolve_base(args.base)
    except ValueError as exc:
        print(f"check_no_hardcoding: {exc}", file=sys.stderr)
        return 1

    hits: list[tuple[str, int, str, str]] = []
    for py in _iter_python_files(base):
        rel = py.relative_to(base)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if py.name in SKIP_FILES:
            continue
        if args.allow_tests and ("test" in py.name or "tests" in rel.parts):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for pat, label in PATTERNS:
                if pat.search(line):
                    hits.append((str(rel), i, line.strip()[:80], label))
                    break

    if not hits:
        print("No hardcoding patterns found.")
        return 0
    print(
        "Possible tenant/country/region hardcoding (use policy/tenant_runtime instead):\n"
    )
    for path, line_no, snippet, label in hits:
        print(f"  {path}:{line_no}  {label}")
        print(f"    {snippet}")
    print(
        f"\nTotal: {len(hits)} hit(s). See docs/architecture/no_hardcoding_checklist.md."
    )
    return 0 if args.exit_zero else 1


if __name__ == "__main__":
    raise SystemExit(main(None))
