#!/usr/bin/env python3
"""
Subprocess / os.system audit (visibility; exit 0).

Writes docs/generated/subprocess_audit.json and .md.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "docs" / "generated" / "subprocess_audit.json"
OUT_MD = ROOT / "docs" / "generated" / "subprocess_audit.md"

SKIP = frozenset(
    {".git", "venv", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".django_test_dbs"}
)

RE_SUB = re.compile(r"\bsubprocess\.([A-Za-z_]+)\s*\(")
RE_OS = re.compile(r"\bos\.(system|popen|popen2)\s*\(")


def _classify(rel: str) -> str:
    if rel.startswith("scripts/"):
        return "deployment_script_safe"
    if "/management/commands/" in rel:
        return "management_command_safe"
    if "/tests/" in rel or rel.endswith("conftest.py"):
        return "test_safe"
    if "/migrations/" in rel:
        return "needs_review"
    return "needs_review"


def main() -> int:
    hits: list[dict[str, str]] = []
    for base in (ROOT / "apps", ROOT / "config", ROOT / "scripts", ROOT / "emis"):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(s in path.parts for s in SKIP):
                continue
            rel = path.relative_to(ROOT).as_posix()
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, start=1):
                m = RE_SUB.search(line)
                if m:
                    hits.append(
                        {
                            "file": rel,
                            "line": str(i),
                            "pattern": f"subprocess.{m.group(1)}",
                            "classification": _classify(rel),
                        }
                    )
                if RE_OS.search(line):
                    hits.append(
                        {
                            "file": rel,
                            "line": str(i),
                            "pattern": "os.system_or_popen",
                            "classification": _classify(rel),
                        }
                    )

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {"hits": len(hits)},
        "hits": sorted(hits, key=lambda h: (h["file"], int(h["line"]))),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary: dict[str, int] = {}
    for h in hits:
        summary[h["classification"]] = summary.get(h["classification"], 0) + 1
    lines = [
        "# Subprocess audit (generated)",
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
    print("audit_subprocess_usage: OK")
    print(f"  written: {OUT_JSON.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
