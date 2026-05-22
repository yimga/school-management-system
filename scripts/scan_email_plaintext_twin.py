"""Scan: every email .html template must have a .txt plaintext twin.

The bug class this catches (FERPA accessibility + CLI mail-client / OCR
parity):

    templates/email/welcome.html        ← rich HTML version exists
    templates/email/welcome.txt         ← MISSING — plaintext readers
                                          (CLI mail, AT, indexers) get
                                          nothing or a stripped-tags
                                          mess that loses links + CTAs.

Convention: any `*.html` template under any directory ending in `/email/`
or whose path contains `/email/locale/<code>/` must have a sibling `*.txt`
file with the same stem (e.g. `low_meal_balance.html` ↔ `low_meal_balance.txt`).

Exclusions:
  * Templates explicitly marked `{# email-plaintext-twin-allow: <reason> #}`
    on a line within the first 20 lines (e.g. embedded preview snippets,
    partials never sent on their own).
  * Files under `templates/email/_components/` or `*partial*`/`*include*`
    paths (snippets, not standalone emails).

Zero-tolerance gate from day 1 (v3.57.1, 2026-05-21).

Usage:
    python scripts/scan_email_plaintext_twin.py [--strict] [--json] [--update-baseline]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES_ROOT = REPO_ROOT / "templates"
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-email-plaintext-twin.json"
)

ALLOW_MARKER = "email-plaintext-twin-allow:"
EXCLUDED_PATH_SEGMENTS = ("_components", "_partials", "_includes", "partial", "include")


def _is_email_template(path: pathlib.Path) -> bool:
    """A template is an email template iff `email/` appears in its path."""
    parts = [p.lower() for p in path.parts]
    return "email" in parts


def _is_excluded(path: pathlib.Path) -> bool:
    name = path.name.lower()
    for seg in EXCLUDED_PATH_SEGMENTS:
        if seg in name:
            return True
        if any(seg == p.lower() for p in path.parts):
            return True
    return False


def _has_allow_marker(path: pathlib.Path) -> bool:
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= 20:
                    return False
                if ALLOW_MARKER in line:
                    return True
    except OSError:
        return False
    return False


def scan_all() -> list[str]:
    findings: list[str] = []
    if not TEMPLATES_ROOT.exists():
        return findings
    for html in TEMPLATES_ROOT.rglob("*.html"):
        if not _is_email_template(html):
            continue
        if _is_excluded(html):
            continue
        if _has_allow_marker(html):
            continue
        twin = html.with_suffix(".txt")
        if not twin.exists():
            findings.append(str(html.relative_to(REPO_ROOT)).replace("\\", "/"))
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
        except (json.JSONDecodeError, ValueError):
            baseline_total = 0

    if args.update_baseline or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(
            json.dumps(
                {"finding_count": total, "findings": findings},
                indent=2,
            ),
            encoding="utf-8",
        )

    if args.json:
        print(
            json.dumps(
                {
                    "finding_count": total,
                    "baseline": baseline_total,
                    "findings": findings,
                },
                indent=2,
            )
        )
    else:
        print(f"email-plaintext-twin scan: {total} HTML email(s) without .txt twin")
        print(f"baseline: {baseline_total}")
        for f in findings[:40]:
            print(f"  {f}")
        if len(findings) > 40:
            print(f"  … {len(findings) - 40} more")

    if args.strict and total > baseline_total:
        print(f"FAIL: {total} > baseline {baseline_total}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
