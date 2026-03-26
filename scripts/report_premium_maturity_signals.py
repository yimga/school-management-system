#!/usr/bin/env python3
"""
Emit premium maturity inventory counts (SOT §0 / ops dashboards).

Scan rules mirror companion linters where noted. This script is report-only unless
--strict runs lint_raw_sql_usage, lint_csrf_exempt_usage, and lint_gilead_residue.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SKIP_SQL = {".git", ".venv", "node_modules", "__pycache__", "migrations", "tests"}
SKIP_CSRF = {".git", ".venv", "node_modules", "__pycache__"}
CSRFPAT = re.compile(r"^\s*@csrf_exempt\b|method_decorator\(\s*csrf_exempt\b")
GILEADPAT = re.compile(r"gilead", re.IGNORECASE)
# External premium proxy (optional); product chat uses Ollama only.
LITELLM_SECRET_NEEDLE = "LITELLM_API_KEY"

# Aligned with scripts/lint_gilead_residue.py (for line-hit totals on the same surface).
GILEAD_SKIP_PARTS = {"migrations", "tests", "__pycache__", "docs", "tmp", "artifacts"}


def _scan_py_files(base: Path, roots: tuple[str, ...], skip_parts: set[str]) -> list[Path]:
    out: list[Path] = []
    for name in roots:
        root = base / name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if any(p in skip_parts for p in path.parts):
                continue
            out.append(path)
    return out


def _gilead_path_skipped(path: Path, root: Path) -> bool:
    if any(part in GILEAD_SKIP_PARTS for part in path.parts):
        return True
    rel = path.relative_to(root).as_posix()
    if "management/commands/" in rel:
        return True
    return False


def _iter_gilead_candidate_files(base: Path) -> list[Path]:
    roots = (
        base / "apps",
        base / "services",
        base / "fixtures",
        base / "templates",
        base / "config",
    )
    extra = (base / "render.yaml", base / "QUICK_START.md")
    found: list[Path] = []
    for r in roots:
        if not r.exists():
            continue
        for path in r.rglob("*"):
            if not path.is_file():
                continue
            if _gilead_path_skipped(path, base):
                continue
            found.append(path)
    for path in extra:
        if path.exists():
            found.append(path)
    return sorted(set(found))


def collect_signals(base: Path) -> dict[str, object]:
    raw_total = 0
    raw_files = 0
    for path in _scan_py_files(base, ("apps", "config"), SKIP_SQL):
        text = path.read_text(encoding="utf-8", errors="replace")
        c = text.count("cursor.execute(")
        if c:
            raw_total += c
            raw_files += 1

    csrf_total = 0
    csrf_files = 0
    for path in _scan_py_files(base, ("apps", "config"), SKIP_CSRF):
        text = path.read_text(encoding="utf-8", errors="replace")
        c = sum(1 for line in text.splitlines() if CSRFPAT.search(line))
        if c:
            csrf_total += c
            csrf_files += 1

    litellm_secret_total = 0
    litellm_secret_files = 0
    for path in _scan_py_files(base, ("apps",), SKIP_SQL):
        text = path.read_text(encoding="utf-8", errors="replace")
        c = text.count(LITELLM_SECRET_NEEDLE)
        if c:
            litellm_secret_total += c
            litellm_secret_files += 1

    gilead_lines = 0
    gilead_files = 0
    for path in _iter_gilead_candidate_files(base):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = sum(1 for line in text.splitlines() if GILEADPAT.search(line))
        if hits:
            gilead_lines += hits
            gilead_files += 1

    return {
        "raw_sql_non_migration": {
            "cursor_execute_hits": raw_total,
            "files_with_hits": raw_files,
        },
        "csrf_exempt": {
            "decorator_line_hits": csrf_total,
            "files_with_hits": csrf_files,
        },
        "litellm_api_key_string": {
            "occurrences_apps_non_migration_non_tests": litellm_secret_total,
            "files_with_hits": litellm_secret_files,
        },
        "gilead_corpus": {
            "line_hits_lint_runtime_surface": gilead_lines,
            "files_with_hits": gilead_files,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report premium maturity signal counts.",
    )
    parser.add_argument("--base", default=".", help="Repo root (default: .)")
    parser.add_argument("--json", action="store_true", help="Print one JSON object to stdout.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Run raw SQL, csrf_exempt, and Gilead linters; exit non-zero if any fail.",
    )
    args = parser.parse_args()
    base = Path(args.base).resolve()
    py = sys.executable

    if args.strict:
        for name in (
            "lint_raw_sql_usage.py",
            "lint_csrf_exempt_usage.py",
            "lint_gilead_residue.py",
        ):
            script = base / "scripts" / name
            r = subprocess.run([py, str(script)], cwd=base)
            if r.returncode != 0:
                return r.returncode

    data = collect_signals(base)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        for section, payload in data.items():
            print(f"[{section}]")
            if isinstance(payload, dict):
                for k, v in sorted(payload.items()):
                    print(f"  {k}: {v}")
            else:
                print(f"  {payload}")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
