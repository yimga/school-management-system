#!/usr/bin/env python3
"""
Raw SQL usage audit: cursor.execute, connection.cursor(, RawSQL( (visibility; exit 0).

Classifies by path heuristics. Cross-check allowlist file when present.
Writes docs/generated/raw_sql_audit.json and .md.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "docs" / "generated" / "raw_sql_audit.json"
OUT_MD = ROOT / "docs" / "generated" / "raw_sql_audit.md"
ALLOW = ROOT / "scripts" / "allowlists" / "raw_sql_allowlist.json"

SKIP = frozenset(
    {".git", "venv", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".django_test_dbs"}
)

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("cursor_execute", re.compile(r"\.cursor\.execute\s*\(")),
    ("connection_cursor", re.compile(r"\.cursor\s*\(\s*\)|connection\.cursor\s*\(")),
    ("raw_sql", re.compile(r"\bRawSQL\s*\(")),
]


def _classify(rel: str) -> str:
    if "/migrations/" in rel:
        return "migration_safe"
    if rel.startswith("scripts/"):
        return "deployment_safe"
    if "/reports/" in rel or rel.startswith("apps/reports/"):
        return "reporting_safe"
    if "/analytics/" in rel or "research_export" in rel:
        return "reporting_safe"
    if rel.startswith("apps/platform_runtime/tests/") or "/tests/" in rel:
        return "test_safe"
    return "needs_review"


def _load_allow(rel: str) -> bool:
    if not ALLOW.is_file():
        return False
    try:
        data = json.loads(ALLOW.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    files = data.get("files") or {}
    entry = files.get(rel)
    return isinstance(entry, dict)


def main() -> int:
    hits: list[dict[str, str]] = []
    for base in (ROOT / "apps", ROOT / "config", ROOT / "emis"):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(s in path.parts for s in SKIP):
                continue
            rel = path.relative_to(ROOT).as_posix()
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                for name, pat in PATTERNS:
                    if pat.search(line):
                        cls = _classify(rel)
                        if _load_allow(rel):
                            cls = "performance_safe"
                        hits.append(
                            {
                                "file": rel,
                                "line": str(i),
                                "pattern": name,
                                "classification": cls,
                            }
                        )

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "allowlist_path": ALLOW.relative_to(ROOT).as_posix() if ALLOW.is_file() else None,
        "totals": {"hits": len(hits)},
        "hits": sorted(hits, key=lambda h: (h["file"], int(h["line"]))),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {}
    for h in hits:
        summary[h["classification"]] = summary.get(h["classification"], 0) + 1
    lines = [
        "# Raw SQL audit (generated)",
        "",
        f"**UTC** `{payload['generated_at']}`",
        "",
        f"**Total hits:** {len(hits)}",
        "",
        "| Classification | Count |",
        "| --- | --- |",
    ]
    for k in sorted(summary.keys()):
        lines.append(f"| {k} | {summary[k]} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("audit_raw_sql_usage: OK")
    print(f"  written: {OUT_JSON.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
