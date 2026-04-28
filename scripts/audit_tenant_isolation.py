#!/usr/bin/env python3
"""
Tenant isolation visibility audit (heuristic; exit 0).

Flags files that reference ``request.school``, ``school_id``, manager URLconf, or
``School.objects`` without obvious ``school=`` filter on the same line (coarse).

Writes docs/generated/tenant_isolation_audit.json and .md.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "docs" / "generated" / "tenant_isolation_audit.json"
OUT_MD = ROOT / "docs" / "generated" / "tenant_isolation_audit.md"

SKIP = frozenset(
    {".git", "venv", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".django_test_dbs"}
)

RE_SCHOOL_REQ = re.compile(r"request\.school|getattr\s*\(\s*request\s*,\s*[\"']school[\"']")
RE_SESSION = re.compile(r"session\[['\"]school_id['\"]\]|school_id")
RE_SCHOOL_OBJ = re.compile(r"\bSchool\.objects\.(get|filter|all)\s*\(")
RE_MANAGER = re.compile(r"manager_urls|manager\.runmycampus|public_host_kind")


def _classify(rel: str, line: str) -> str:
    if "config/manager_urls.py" in rel or rel.endswith("manager_urls.py"):
        return "manager_scoped"
    if "middleware" in rel and "schools" in rel:
        return "global_safe"
    if RE_SCHOOL_OBJ.search(line) and "school=" not in line and "school__" not in line:
        return "needs_review"
    if RE_SCHOOL_REQ.search(line) or RE_SESSION.search(line):
        return "tenant_scoped"
    if RE_MANAGER.search(line):
        return "manager_scoped"
    return "global_safe"


def main() -> int:
    hits: list[dict[str, str]] = []
    for base in (ROOT / "apps", ROOT / "config"):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(s in path.parts for s in SKIP):
                continue
            if "/migrations/" in path.as_posix():
                continue
            rel = path.relative_to(ROOT).as_posix()
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, start=1):
                if not (
                    RE_SCHOOL_REQ.search(line)
                    or RE_SESSION.search(line)
                    or RE_SCHOOL_OBJ.search(line)
                    or RE_MANAGER.search(line)
                ):
                    continue
                hits.append(
                    {
                        "file": rel,
                        "line": str(i),
                        "classification": _classify(rel, line),
                        "preview": line.strip()[:240],
                    }
                )

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {"hits": len(hits)},
        "hits": sorted(hits, key=lambda h: (h["file"], int(h["line"])))[:5000],
        "truncated": len(hits) > 5000,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary: dict[str, int] = {}
    for h in hits:
        summary[h["classification"]] = summary.get(h["classification"], 0) + 1
    lines = [
        "# Tenant isolation audit (generated)",
        "",
        f"**UTC** `{payload['generated_at']}`",
        "",
        f"**Total hits (capped in JSON):** {len(hits)}",
        "",
        "| Classification | Count |",
        "| --- | --- |",
    ]
    for k in sorted(summary.keys()):
        lines.append(f"| {k} | {summary[k]} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("audit_tenant_isolation: OK")
    print(f"  written: {OUT_JSON.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
