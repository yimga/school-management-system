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
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION_DOC = ROOT / "docs" / "GILEAD_REFERENCE_CLASSIFICATION.md"
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


def _iter_classifiable_files(root: Path):
    """Walk repo without descending into vendor/cache trees (rglob is too slow)."""
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
    return False


def main() -> int:
    errors: list[str] = []

    if not CLASSIFICATION_DOC.is_file():
        errors.append("Missing docs/GILEAD_REFERENCE_CLASSIFICATION.md")
    else:
        doc_text = CLASSIFICATION_DOC.read_text(encoding="utf-8", errors="replace")
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

    for path in _iter_classifiable_files(ROOT):
        rel = path.relative_to(ROOT).as_posix()
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
    raise SystemExit(main())
