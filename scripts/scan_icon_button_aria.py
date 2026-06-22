#!/usr/bin/env python3
"""Zero-tolerance gate: icon-only <button>/<a> must carry an accessible name.

An interactive control whose ONLY content is an icon (`<i class="bi ...">` or an
`<svg>`) with no visible text AND no `aria-label` / `aria-labelledby` / `title`
is invisible to screen-reader users (WCAG 4.1.2 Name, Role, Value). This scanner
flags such controls across templates/.

Mark an intentional exception with `<!-- icon-aria-allow: <reason> -->` on the
control's line or the line directly above it.

Usage:
  python scripts/scan_icon_button_aria.py            # report + exit 1 if over baseline
  python scripts/scan_icon_button_aria.py --json     # machine-readable
  python scripts/scan_icon_button_aria.py --update-baseline
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"
BASELINE = REPO / "var" / "security-audit-baseline-icon-button-aria.json"
ALLOW = "icon-aria-allow"

# A <button>/<a> with no accessible-name attribute whose content is only an icon.
ICON_ONLY = re.compile(
    r"<(button|a)\b"
    r"(?![^>]*\baria-label=)"
    r"(?![^>]*\baria-labelledby=)"
    r"(?![^>]*\btitle=)"
    r"[^>]*>\s*"
    r'(?:<i\s+[^>]*\bclass="[^"]*\bbi\b[^"]*"[^>]*>\s*</i>|<svg\b[^>]*>.*?</svg>)\s*'
    r"</\1>",
    re.IGNORECASE | re.DOTALL,
)


def scan_text(text: str) -> list[int]:
    lines = text.splitlines()
    out: list[int] = []
    for m in ICON_ONLY.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        ctx = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        if line_no >= 2:
            ctx += " " + lines[line_no - 2]
        if ALLOW in ctx:
            continue
        out.append(line_no)
    return out


def collect() -> list[str]:
    findings: list[str] = []
    for p in sorted(TEMPLATES.rglob("*.html")):
        for ln in scan_text(p.read_text(encoding="utf-8", errors="replace")):
            findings.append(f"{p.relative_to(REPO).as_posix()}:{ln}")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args()

    findings = collect()
    count = len(findings)

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps({"finding_count": count, "findings": findings}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"baseline updated: finding_count={count}")
        return 0

    if args.json:
        print(json.dumps({"finding_count": count, "findings": findings}, indent=2))
        return 0

    print(f"icon-only controls without an accessible name: {count}")
    for f in findings[:60]:
        print(f"  {f}")

    baseline = 0
    if BASELINE.exists():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8")).get("finding_count", 0)
    if count > baseline:
        print(f"FAIL: {count} > baseline {baseline} — add aria-label/title or an "
              f"<!-- {ALLOW}: reason --> marker.")
        return 1
    print(f"OK (baseline {baseline})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
