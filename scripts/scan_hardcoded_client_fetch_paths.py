#!/usr/bin/env python3
"""Scan: hardcoded product fetch/beacon paths in client JS/TS (cascade drift gate).

Flags ``fetch("`` / ``fetch(` `` / ``sendBeacon("`` when the path starts with a
product prefix that must come from page-data or RMCPlatformSurface:

  /api/  /assist-dock/  /portal/ai/stream  /emis/api/

Exempt:
  - ``static/js/service-worker.js`` (offline path-prefix infrastructure)
  - Lines with ``client-fetch-allow: <reason>`` marker

Zero-tolerance: baseline ships at 0; CI ``--strict`` fails on net-new findings.

Usage:
    python scripts/scan_hardcoded_client_fetch_paths.py [--strict] [--json] [--update-baseline]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-hardcoded-client-fetch.json"

ALLOW_MARKER = "client-fetch-allow:"
EXEMPT_FILES = frozenset(
    {
        "static/js/service-worker.js",
    }
)

SCAN_DIRS = (
    REPO_ROOT / "static" / "js",
    REPO_ROOT / "src",
)

# fetch('/api/...') or fetch(`/api/...`
LITERAL_RE = re.compile(
    r"""(?:fetch|sendBeacon)\s*\(\s*['"]((?:/api/|/assist-dock/|/portal/ai/stream|/emis/api/)[^'"]*)['"]""",
)
TEMPLATE_RE = re.compile(
    r"""(?:fetch|sendBeacon)\s*\(\s*`((?:/api/|/assist-dock/|/portal/ai/stream|/emis/api/)[^`$]*)""",
)


def _scan_file(path: pathlib.Path) -> list[str]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    if rel in EXEMPT_FILES:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    findings: list[str] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARKER in line:
            continue
        for pattern in (LITERAL_RE, TEMPLATE_RE):
            match = pattern.search(line)
            if match:
                findings.append(
                    f"{rel}:{line_no}: hardcoded client path {match.group(1)!r}"
                )
                break
    return findings


def scan_all() -> list[str]:
    findings: list[str] = []
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in {".js", ".ts", ".tsx"}:
                continue
            if "/node_modules/" in path.as_posix():
                continue
            findings.extend(_scan_file(path))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = scan_all()
    total = len(findings)

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    baseline_total = 0
    if BASELINE_PATH.exists():
        try:
            baseline_total = int(
                json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get(
                    "finding_count", 0
                )
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            baseline_total = 0

    if args.update_baseline or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(
            json.dumps({"finding_count": total, "findings": findings}, indent=2),
            encoding="utf-8",
        )

    if args.json:
        print(
            json.dumps(
                {"finding_count": total, "baseline": baseline_total, "findings": findings},
                indent=2,
            )
        )
    else:
        print(f"hardcoded-client-fetch scan: {total} violation(s)")
        print(f"baseline: {baseline_total}")
        for item in findings[:40]:
            print(f"  {item}")

    if args.strict and total > baseline_total:
        print(f"FAIL: {total} > baseline {baseline_total}", file=sys.stderr)
        return 1
    if total == 0:
        print("HARDCODED_CLIENT_FETCH_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
