#!/usr/bin/env python3
"""Fail CI when wallpaper status badges reappear (MAX Wave 4).

Flags:
  - Template ``status_badge_text=_("Operational")`` / ``"Operational"``
  - Catalog ``"status": "ready"`` in TENANT_CONFIGURATION_SECTIONS static tuples
    (enrichment must supply live labels — static ready in the catalog tuple is banned)

Usage:
  python scripts/scan_wallpaper_status_badges.py
  python scripts/scan_wallpaper_status_badges.py --compare
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "var" / "security-audit-baseline-wallpaper-status-badges.json"

OPERATIONAL_RE = re.compile(
    r"status_badge_text\s*=\s*(?:_\(\s*)?[\"']Operational[\"']",
    re.IGNORECASE,
)
# Static ready in the catalog constant body (not in enrich_* live maps).
READY_CATALOG_RE = re.compile(
    r'TENANT_CONFIGURATION_SECTIONS[\s\S]{0,8000}?"status"\s*:\s*"ready"',
    re.IGNORECASE,
)


def scan() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in (ROOT / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if OPERATIONAL_RE.search(line):
                findings.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "line": str(i),
                        "kind": "operational-wallpaper",
                        "snippet": line.strip()[:160],
                    }
                )
    catalog = ROOT / "apps" / "platform_runtime" / "administration_catalog.py"
    if catalog.exists():
        text = catalog.read_text(encoding="utf-8", errors="ignore")
        # Only the sections tuple — not MODULE status enums elsewhere.
        if '"status": "ready"' in text or "'status': 'ready'" in text:
            # Allow ready only outside TENANT_CONFIGURATION_SECTIONS block.
            start = text.find("TENANT_CONFIGURATION_SECTIONS")
            end = text.find("def enriched_modules", start)
            block = text[start:end] if start >= 0 else ""
            if re.search(r'["\']status["\']\s*:\s*["\']ready["\']', block):
                findings.append(
                    {
                        "path": catalog.relative_to(ROOT).as_posix(),
                        "line": "0",
                        "kind": "catalog-ready-wallpaper",
                        "snippet": "TENANT_CONFIGURATION_SECTIONS contains static status ready",
                    }
                )
    # Default args that reintroduce Operational
    for rel in (
        "apps/platform_runtime/super_operational_frames.py",
        "apps/platform_runtime/templatetags/operational_frame_tags.py",
    ):
        path = ROOT / rel
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "Operational" in line and (
                "status_badge" in line or "status_badge_text" in line
            ):
                findings.append(
                    {
                        "path": rel,
                        "line": str(i),
                        "kind": "python-default-wallpaper",
                        "snippet": line.strip()[:160],
                    }
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = scan()
    payload = {"finding_count": len(findings), "findings": findings}
    if args.json:
        print(json.dumps(payload, indent=2))
    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline {BASELINE} count={len(findings)}")
        return 0
    if args.compare:
        if not BASELINE.exists():
            print("MISSING baseline", BASELINE, file=sys.stderr)
            return 1
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        base_n = int(base.get("finding_count", 0))
        cur_n = len(findings)
        if cur_n > base_n:
            print(f"REGRESSION wallpaper badges {base_n} -> {cur_n}", file=sys.stderr)
            for f in findings[:20]:
                print(f"  {f['path']}:{f['line']} {f['kind']}", file=sys.stderr)
            return 1
        print(f"OK wallpaper badges {cur_n} (baseline {base_n})")
        return 0
    if findings:
        print(f"FOUND {len(findings)} wallpaper badge sites", file=sys.stderr)
        for f in findings[:30]:
            print(f"  {f['path']}:{f['line']} [{f['kind']}] {f['snippet']}", file=sys.stderr)
        return 1
    print("OK: 0 wallpaper status badges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
