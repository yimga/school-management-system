#!/usr/bin/env python3
"""
Query hotspot heuristics (visibility; exit 0).

Scores view/service files by density of ORM calls vs select_related / prefetch_related.
Does not prove N+1; use for profiling backlog only.

Writes docs/generated/query_hotspots_audit.json and .md.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "docs" / "generated" / "query_hotspots_audit.json"
OUT_MD = ROOT / "docs" / "generated" / "query_hotspots_audit.md"

SKIP = frozenset(
    {".git", "venv", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".django_test_dbs"}
)

HOT_SUBSTR = ("dashboard", "report", "evidence", "portal", "widget", "aggregate")
RE_OBJECTS = re.compile(r"\.objects\.")
RE_SEL = re.compile(r"select_related\s*\(")
RE_PREF = re.compile(r"prefetch_related\s*\(")


def _score(text: str) -> tuple[int, int, int, str]:
    o = len(RE_OBJECTS.findall(text))
    s = len(RE_SEL.findall(text))
    p = len(RE_PREF.findall(text))
    if o == 0:
        return 0, o, s + p, "low"
    ratio = (s + p) / max(o, 1)
    if ratio >= 0.35:
        return ratio, o, s + p, "low"
    if ratio >= 0.15:
        return ratio, o, s + p, "medium"
    if o > 40:
        return ratio, o, s + p, "high"
    return ratio, o, s + p, "needs_profiling"


def main() -> int:
    rows: list[dict[str, object]] = []
    for base in (ROOT / "apps",):
        for path in sorted(base.rglob("*.py")):
            if any(x in path.parts for x in SKIP):
                continue
            if "/migrations/" in path.as_posix() or "/tests/" in path.as_posix():
                continue
            rel = path.relative_to(ROOT).as_posix().lower()
            if not any(h in rel for h in HOT_SUBSTR):
                continue
            if not (rel.endswith("views.py") or "views_" in Path(rel).name or "services.py" in rel):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            ratio, o, sp, tier = _score(text)
            rows.append(
                {
                    "file": path.relative_to(ROOT).as_posix(),
                    "objects_calls": o,
                    "select_prefetch_calls": sp,
                    "prefetch_ratio": round(ratio, 4),
                    "classification": tier,
                }
            )

    rows.sort(key=lambda r: (r["classification"] == "high", r["objects_calls"]), reverse=True)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {"files_scored": len(rows)},
        "files": rows[:400],
        "truncated": len(rows) > 400,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary: dict[str, int] = {}
    for r in rows:
        summary[str(r["classification"])] = summary.get(str(r["classification"]), 0) + 1
    lines = [
        "# Query hotspots audit (generated)",
        "",
        f"**UTC** `{payload['generated_at']}`",
        "",
        "| Classification | Files |",
        "| --- | --- |",
    ]
    for k in sorted(summary.keys()):
        lines.append(f"| {k} | {summary[k]} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("audit_query_hotspots: OK")
    print(f"  written: {OUT_JSON.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
