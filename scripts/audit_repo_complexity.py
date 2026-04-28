#!/usr/bin/env python3
"""
Repo complexity audit: counts + coarse risk buckets (visibility only; exit 0).

Writes docs/generated/repo_complexity_audit.json and .md.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "docs" / "generated" / "repo_complexity_audit.json"
OUT_MD = ROOT / "docs" / "generated" / "repo_complexity_audit.md"

SKIP_DIR = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".django_test_dbs",
        "htmlcov",
        "dist",
        "build",
    }
)

RE_PRINT = re.compile(r"\bprint\s*\(")
RE_EXC = re.compile(r"except\s+Exception\b")
RE_SUB = re.compile(r"\bsubprocess\.")
RE_OS = re.compile(r"\bos\.system\s*\(")
RE_CURSOR = re.compile(r"\.cursor\.execute\s*\(")
RE_GILEAD = re.compile(r"gilead", flags=re.IGNORECASE)
RE_GEMINI = re.compile(r"GEMINI_API_KEY")


def _walk_files(root: Path, suffix: str) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob(f"*{suffix}"):
        if any(x in p.parts for x in SKIP_DIR):
            continue
        if not p.is_file():
            continue
        out.append(p)
    return sorted(out)


def _tier(rel: str, hits: dict[str, int]) -> str:
    if hits["gilead"] and rel.startswith("templates/") and "/admin/" not in rel:
        return "needs_review"
    if hits["cursor_execute"] and "/migrations/" not in rel:
        return "needs_review"
    if hits["print"] and rel.startswith("apps/") and "/tests/" not in rel:
        return "controlled"
    if hits["except_exception"] > 2:
        return "needs_review"
    return "safe"


def main() -> int:
    py_files = _walk_files(ROOT / "apps", ".py") + _walk_files(ROOT / "config", ".py") + _walk_files(ROOT / "emis", ".py")
    html_files = _walk_files(ROOT / "templates", ".html")
    md_files = _walk_files(ROOT / "docs", ".md")
    mig_files = [p for p in _walk_files(ROOT / "apps", ".py") if "/migrations/" in p.as_posix()]

    counters = Counter(
        {
            "python_files": len(py_files),
            "html_templates": len(html_files),
            "markdown_docs": len(md_files),
            "migration_py_files": len(mig_files),
        }
    )

    agg = defaultdict(int)
    per_file: list[dict[str, object]] = []
    for p in py_files:
        rel = p.relative_to(ROOT).as_posix()
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = {
            "print": len(RE_PRINT.findall(text)),
            "except_exception": len(RE_EXC.findall(text)),
            "subprocess": len(RE_SUB.findall(text)),
            "os_system": len(RE_OS.findall(text)),
            "cursor_execute": len(RE_CURSOR.findall(text)),
            "gilead": len(RE_GILEAD.findall(text)),
            "gemini_key": len(RE_GEMINI.findall(text)),
        }
        for k, v in hits.items():
            agg[k] += v
        if sum(hits.values()):
            per_file.append(
                {
                    "file": rel,
                    "hits": hits,
                    "governance_tier": _tier(rel, hits),
                }
            )

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary_counts": dict(counters),
        "aggregate_hits": dict(sorted(agg.items())),
        "top_files_by_total_hits": sorted(
            per_file,
            key=lambda r: sum((r["hits"] or {}).values()),
            reverse=True,
        )[:200],
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Repo complexity audit (generated)",
        "",
        f"**UTC** `{payload['generated_at']}`",
        "",
        "## Counts",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    for k, v in sorted(payload["summary_counts"].items()):
        lines.append(f"| {k} | {v} |")
    lines.extend(["", "## Aggregate hits (substring scans)", ""])
    for k, v in sorted(payload["aggregate_hits"].items()):
        lines.append(f"- **{k}:** {v}")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("audit_repo_complexity: OK")
    print(f"  written: {OUT_JSON.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
