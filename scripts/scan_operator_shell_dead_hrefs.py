#!/usr/bin/env python3
"""Scan: dead ``href="#"`` in operator-facing template chrome (zero-tolerance).

Targets navigation chrome where a dead hash bricks Help/RBAC/header flows:
``templates/components/``, ``templates/partials/``, and the five dashboard shells.

Allowed when the same ``<a>`` tag (or parent with ``data-rmc-dead-link-allow``) has:
  - ``data-bs-toggle`` / ``data-toggle`` (Bootstrap modal/tab)
  - ``data-rmc-dead-link-allow: <reason>`` on the anchor or an ancestor
  - ``<!-- dead-href-allow: <reason> -->`` on the preceding line

Usage:
    python scripts/scan_operator_shell_dead_hrefs.py [--strict] [--update-baseline]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "var" / "security-audit-baseline-operator-shell-dead-hrefs.json"

SCAN_DIRS = (
    ROOT / "templates" / "components",
    ROOT / "templates" / "partials",
)
SHELL_FILES = (
    ROOT / "templates" / "control_plane_skeleton.html",
    ROOT / "templates" / "portal_base.html",
    ROOT / "templates" / "base.html",
    ROOT / "templates" / "marketing" / "base_marketing.html",
    ROOT / "templates" / "admin" / "base_site.html",
    ROOT / "templates" / "components" / "user_dropdown.html",
)

ANCHOR_RE = re.compile(r"<a\b[^>]*\bhref\s*=\s*['\"]#['\"][^>]*>", re.IGNORECASE | re.DOTALL)
ALLOW_ATTR = "data-rmc-dead-link-allow"
ALLOW_COMMENT = "dead-href-allow:"
TOGGLE_ATTRS = ("data-bs-toggle", "data-toggle")


def _html_files() -> list[Path]:
    paths: list[Path] = []
    for d in SCAN_DIRS:
        if d.is_dir():
            paths.extend(sorted(d.rglob("*.html")))
    for p in SHELL_FILES:
        if p.is_file():
            paths.append(p)
    return paths


def _line_no(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _is_allowed(text: str, start: int, end: int) -> bool:
    tag = text[start:end]
    if any(attr in tag for attr in TOGGLE_ATTRS):
        return True
    if ALLOW_ATTR in tag:
        return True
    window_start = max(0, start - 400)
    window = text[window_start:end]
    if ALLOW_ATTR in window:
        return True
    prev_line_start = text.rfind("\n", 0, start - 1) + 1
    prev_line = text[prev_line_start:start]
    if ALLOW_COMMENT in prev_line:
        return True
    return False


def scan() -> list[dict]:
    findings: list[dict] = []
    for path in _html_files():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in ANCHOR_RE.finditer(text):
            if _is_allowed(text, match.start(), match.end()):
                continue
            findings.append(
                {
                    "file": rel,
                    "line": _line_no(text, match.start()),
                    "snippet": match.group(0)[:120],
                }
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail on any finding")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings = scan()
    count = len(findings)

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps({"finding_count": count, "findings": findings}, indent=2),
            encoding="utf-8",
        )
        print(f"Updated baseline: {count} findings -> {BASELINE}")
        return 0

    baseline_count = 0
    if BASELINE.is_file():
        baseline_count = int(json.loads(BASELINE.read_text(encoding="utf-8")).get("finding_count", 0))

    print(f"scan_operator_shell_dead_hrefs: {count} finding(s) (baseline {baseline_count})")
    for f in findings[:20]:
        print(f"  {f['file']}:{f['line']} {f['snippet'][:80]}")
    if len(findings) > 20:
        print(f"  ... and {len(findings) - 20} more")

    if args.strict and count > baseline_count:
        return 1
    if count > baseline_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
