#!/usr/bin/env python3
"""
Scan Python sources for handlers that declare POST-processing decorators.

This is visibility for governance (POST route classification), not runtime enforcement.
Writes ``docs/generated/post_handler_audit.json``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_JSON = REPO / "docs" / "generated" / "post_handler_audit.json"

SKIP_PREFIXES = (
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".django_test_dbs",
)


def _bucket(rel: str) -> str:
    if "/tests/" in rel or (
        rel.startswith("apps/")
        and ("test_" in Path(rel).name or "/test_" in rel)
    ):
        return "tests"
    if rel.startswith("scripts/"):
        return "scripts"
    return "product"


_POST_LINE = re.compile(
    r"@require_POST\b|@require_http_methods\b|require_http_methods\s*\("
)


def _looks_like_post_decorator(block: str) -> bool:
    """True if decorators mention POST-capable handlers."""
    if "@require_POST" in block:
        return True
    if "require_http_methods" in block:
        # Single-line POST list or multi-line containing POST
        return bool(re.search(r"[\"']POST[\"']", block))
    return False


_PROTECTIVE = (
    "@login_required",
    "@user_passes_test",
    "@permission_required",
    "@staff_member_required",
)


def _has_protective_decorator_above(lines: list[str], line_idx: int, lookback: int = 80) -> bool:
    start = max(0, line_idx - lookback)
    chunk = lines[start:line_idx]
    # Scan backwards for decorator stack before ``def``
    deco_block: list[str] = []
    for j in range(len(chunk) - 1, -1, -1):
        s = chunk[j].strip()
        if s.startswith("def ") or s.startswith("async def"):
            break
        if s.startswith("@") or s.startswith("class "):
            deco_block.append(s)
        elif s.startswith("def ") or s.startswith("async def"):
            break
    text = "\n".join(chunk)
    return any(p in text for p in _PROTECTIVE)


def _classification(*, bucket: str, protective: bool) -> str:
    if bucket == "tests":
        return "allowed_tests"
    if bucket == "scripts":
        return "scripts_cli"
    if protective:
        return "protected_candidate"
    return "needs_review"


def _iter_py_files():
    for dirpath, _dirnames, filenames in os.walk(REPO):
        p = Path(dirpath)
        try:
            rel_parts = p.relative_to(REPO).parts
        except ValueError:
            continue
        if rel_parts and str(rel_parts[0]).startswith("."):
            continue
        rel_join = "/".join(rel_parts)
        if any(seg in rel_join for seg in SKIP_PREFIXES):
            continue
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            yield p / fn


def main() -> int:
    rows = []
    by_bucket: dict[str, int] = defaultdict(int)
    by_class: dict[str, int] = defaultdict(int)

    for path in sorted(_iter_py_files()):
        rel = path.relative_to(REPO).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not _POST_LINE.search(line):
                continue
            # Expand small window for multi-line require_http_methods
            window = "\n".join(lines[i : min(len(lines), i + 12)])
            if not _looks_like_post_decorator(window):
                continue
            bucket = _bucket(rel)
            protective = _has_protective_decorator_above(lines, i)
            cls = _classification(bucket=bucket, protective=protective)
            rows.append(
                {
                    "file": rel,
                    "line": str(i + 1),
                    "bucket": bucket,
                    "classification": cls,
                    "protective_decorator_nearby": protective,
                }
            )
            by_bucket[bucket] += 1
            by_class[cls] += 1

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary_by_bucket": dict(sorted(by_bucket.items())),
        "summary_by_classification": dict(sorted(by_class.items())),
        "totals": {"hits": len(rows)},
        "rows": sorted(rows, key=lambda r: (r["file"], int(r["line"]))),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("audit_post_handler_surface: OK")
    print(f"  written: {OUT_JSON.as_posix()}")
    print(f"  hits: {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
