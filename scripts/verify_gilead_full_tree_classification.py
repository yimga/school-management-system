#!/usr/bin/env python3
"""
Full-tree Gilead reference classification verifier (Phase 12 depth).

Goal:
- keep runtime/product surfaces clean (already covered by lint_gilead_residue.py)
- additionally ensure any remaining full-tree references stay in classified
  historical/tooling buckets documented in docs/GILEAD_REFERENCE_CLASSIFICATION.md
- scan ``.po`` locale catalogs and ``apps/**/fixtures/**`` as explicit buckets (legacy msgids / seed JSON).

Traversal uses os.walk with directory pruning (node_modules, .git, venvs, caches)
so the gate stays fast; classification rules are unchanged.

Run (from repo root):
  python scripts/verify_gilead_full_tree_classification.py
Optional ``--base`` overrides the repository root (default: directory containing this script's parent).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = ROOT

NEEDLE = re.compile(r"gilead", flags=re.IGNORECASE)

# Prune these directory names during traversal (avoid scanning vendor trees).
_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
        "htmlcov",
        ".django_test_dbs",
        ".tmp",
        "tmp",
        "logs",
        "backups",
        "eggs",
        ".eggs",
    }
)

# Keep scope text-like and deterministic.
TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".json",
    ".html",
    ".yml",
    ".yaml",
    ".txt",
    ".toml",
    ".ini",
    ".cfg",
    ".js",
    ".po",
}


def _should_skip_path(rel: str) -> bool:
    # Generated / transient artifacts are not source-of-truth classification targets.
    prefixes = (
        ".django_test_dbs/",
        ".tmp/",
        "tmp/",
        "logs/",
        "backups/",
    )
    if rel.startswith(prefixes):
        return True
    if rel in {"full_test_run.txt", "gate_log.txt", "gate_log2.txt", "test_output.txt"}:
        return True
    return False


@lru_cache(maxsize=None)
def _tracked_file_relpaths(root: Path) -> frozenset[str] | None:
    """Prefer tracked files so untracked scratch artifacts do not fail the verifier."""
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


def _iter_classifiable_files(root: Path):
    """Walk repo without descending into vendor/cache trees (rglob is too slow)."""
    tracked = _tracked_file_relpaths(root)
    if tracked is not None:
        for rel in sorted(tracked):
            path = root / Path(rel)
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            yield path
        return
    root_s = os.fspath(root.resolve())
    for dirpath, dirnames, filenames in os.walk(
        root_s, topdown=True, followlinks=False
    ):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in _SKIP_DIR_NAMES and not d.endswith(".egg-info")
        ]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            yield path


def _is_allowed_reference_path(rel: str) -> bool:
    # 1) Docs / archive / operational narratives
    if rel.startswith("docs/"):
        return True
    # 2) Historical migrations
    if rel.startswith("apps/") and "/migrations/" in rel:
        return True
    # 3) Tests / fixtures
    if rel.startswith("tests/"):
        return True
    if rel.startswith("apps/") and "/tests/" in rel:
        return True
    if rel.startswith("apps/") and "/fixtures/" in rel:
        return True
    if rel.endswith("/tests.py") or rel.endswith("tests.py"):
        return True
    # 4) Management commands (deprecated wrappers allowed)
    if rel.startswith("apps/") and "/management/commands/" in rel:
        return True
    # 5) Locale catalogs (legacy msgids; runtime copy still lint-scoped via templates/apps)
    if rel.startswith("locale/"):
        return True
    # 6) Tooling scripts and generated audit artifacts
    if rel.startswith("scripts/"):
        return True
    # 7) CI workflows (may invoke audit scripts whose paths contain "gilead")
    if rel.startswith(".github/workflows/"):
        return True
    # 8) Cursor planning/rules artifacts
    if rel.startswith(".cursor/"):
        return True
    # 9) Vendored dictionaries and tracked verifier logs are not product copy.
    if rel.startswith("static/vendor/"):
        return True
    if rel.startswith("var/"):
        return True
    return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that full-tree 'gilead' references are contained in allowed "
            "historical/tooling buckets."
        )
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root to scan (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_gilead_full_tree_classification: FAIL\n  - {exc}", file=sys.stderr)
        return 1

    classification_doc = root / "docs" / "GILEAD_REFERENCE_CLASSIFICATION.md"
    errors: list[str] = []

    if not classification_doc.is_file():
        errors.append("Missing docs/GILEAD_REFERENCE_CLASSIFICATION.md")
    else:
        doc_text = classification_doc.read_text(encoding="utf-8", errors="replace")
        for token in (
            "Archive / root_history",
            "Migrations (historical)",
            "Lint-scoped runtime",
            "Management commands",
            "Inventory / audit scripts",
            "Corpus hygiene program",
            "P0 — Live surfaces",
        ):
            if token not in doc_text:
                errors.append(
                    "docs/GILEAD_REFERENCE_CLASSIFICATION.md missing section: "
                    f"{token!r}"
                )

    total_hits = 0
    disallowed: list[str] = []

    for path in _iter_classifiable_files(root):
        rel = path.relative_to(root).as_posix()
        if _should_skip_path(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if not NEEDLE.search(text):
            continue
        total_hits += 1
        if not _is_allowed_reference_path(rel):
            disallowed.append(rel)

    if disallowed:
        errors.append(
            "Unclassified full-tree 'gilead' references outside allowed buckets:\n  - "
            + "\n  - ".join(sorted(disallowed)[:50])
        )
        if len(disallowed) > 50:
            errors.append(
                f"... and {len(disallowed) - 50} additional path(s); tighten classification."
            )

    if errors:
        print("verify_gilead_full_tree_classification: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "verify_gilead_full_tree_classification: PASS "
        f"(classified full-tree refs, files_with_hit={total_hits})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
