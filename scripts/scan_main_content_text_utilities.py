#!/usr/bin/env python3
"""Baseline scan: text-white/text-dark in main-content template zones (not chrome)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "var/security-audit-baseline-main-content-text-utilities.json"

SCAN_ROOTS = (
    REPO / "templates/siteconfig",
    REPO / "templates/schools",
    REPO / "templates/platform_runtime",
    REPO / "templates/admin",
    REPO / "templates/portal",
)

CHROME_SKIP = re.compile(
    r"(control_plane_sidebar|manager_operator_topbar|marketing|offcanvas|navbar|statement-header)",
    re.I,
)

PATTERN = re.compile(r"\b(text-white(?:-50|-75)?|text-dark)\b")

DARK_SURFACE_TOKENS = ("bg-dark", "bg-secondary", "bg-black", "bg-primary")
LIGHT_BADGE_TOKENS = ("bg-light", "bg-white", "bg-warning")
COLORED_BADGE_TOKENS = ("bg-info", "bg-success", "bg-danger", "bg-red", "bg-primary")


def is_intentional(line: str, utility: str) -> bool:
    if utility == "text-dark" and any(tok in line for tok in LIGHT_BADGE_TOKENS + COLORED_BADGE_TOKENS):
        return True
    if utility.startswith("text-white") and any(tok in line for tok in DARK_SURFACE_TOKENS):
        return True
    if utility == "text-white-50" and "bg-dark" in line:
        return True
    if utility.startswith("text-white") and any(tok in line for tok in COLORED_BADGE_TOKENS):
        return True
    if utility.startswith("text-white") and (
        "school-primary" in line or "card-header text-white" in line
    ):
        return True
    if "modal-title" in line and utility == "text-white":
        return True
    return False


def findings() -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.html")):
            if CHROME_SKIP.search(path.name):
                continue
            rel = path.relative_to(REPO).as_posix()
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for match in PATTERN.finditer(line):
                    utility = match.group(1)
                    if is_intentional(line, utility):
                        continue
                    rows.append(
                        {
                            "file": rel,
                            "line": lineno,
                            "utility": utility,
                            "snippet": line.strip()[:160],
                        }
                    )
    return rows


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    current = findings()
    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps({"finding_count": len(current), "findings": current}, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote baseline {len(current)} findings -> {BASELINE.relative_to(REPO)}")
        return 0
    if not BASELINE.is_file():
        print("scan_main_content_text_utilities: missing baseline; run with --write-baseline", file=sys.stderr)
        return 1
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    allowed = int(baseline.get("finding_count", len(baseline.get("findings", []))))
    count = len(current)
    if count > allowed:
        print(f"FAIL scan_main_content_text_utilities: {count} > baseline {allowed}", file=sys.stderr)
        for row in current[:25]:
            print(f"  {row['file']}:{row['line']} {row['utility']}", file=sys.stderr)
        return 1
    print(f"OK scan_main_content_text_utilities ({count} <= {allowed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
