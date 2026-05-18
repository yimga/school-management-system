"""Scan: detect the position:sticky + overflow:hidden truncation trap.

The bug shape (caught in v3.27.1 on `.theme-experience-right` in
phase2-control-plane-bundle.css and phase2-portal-bundle.css):

    .X {
        position: sticky;
        top: ...;
        overflow: hidden;     ← these two combined truncate the bottom
    }                            of the column whenever its content
                                 exceeds viewport height. Sticky pins
                                 the top; overflow:hidden clips the
                                 rest; the user can't reach it.

This scanner walks every CSS rule block in `static/css/` and
`static/marketing/css/` and flags any rule whose declaration body
contains BOTH `position: sticky` AND `overflow: hidden`. The combo is
almost always wrong on a tall element. If you genuinely need both
(e.g. a small sticky badge strip with horizontal overflow), mark the
declaration with `/* sticky-overflow-allow: <reason> */` on either
line — categorical allow-marker pattern matches the rest of the
scanner family.

Zero-tolerance gate from day 1.

Usage:
    python scripts/scan_sticky_with_overflow_hidden.py [--strict] [--json]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS_DIRS = [
    REPO_ROOT / "static" / "css",
    REPO_ROOT / "static" / "marketing" / "css",
]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-sticky-with-overflow-hidden.json"

# Match a CSS rule block: selector(s) { ...declarations... }.
# Reject `@` at-rules (@media, @keyframes, @supports) — they contain
# nested blocks; we'll recurse into their inner rules via the same regex.
RULE_RE = re.compile(r"([^{}@]+)\{([^{}]*)\}", re.DOTALL)
STICKY_RE = re.compile(r"position\s*:\s*sticky\b")
# Vertical-axis clipping is what truncates content the user can't reach when
# combined with sticky. Catch BOTH the bare `overflow: hidden` (clips both
# axes) AND the explicit `overflow-y: hidden`.
OVERFLOW_Y_CLIP_RE = re.compile(r"overflow(?:-y)?\s*:\s*hidden\b")
# Legitimate escape: vertical scroll declared on the same element (sidebars,
# internally-scrolling columns). If `overflow-y: auto|scroll` is present, the
# element gives the user a way to reach all content.
OVERFLOW_Y_SCROLL_RE = re.compile(r"overflow(?:-y)?\s*:\s*(?:auto|scroll)\b")
ALLOW_MARKER = "sticky-overflow-allow:"


def _strip_comments(text: str) -> str:
    return re.sub(r"/\*(?!.*sticky-overflow-allow:).*?\*/", "", text, flags=re.DOTALL)


def _scan_css_text(path: pathlib.Path, text: str) -> list[str]:
    findings: list[str] = []
    # Walk every brace block. We don't try to climb at-rules; the regex
    # picks up nested rules (e.g. inside @media) on subsequent passes
    # because the brace pairing is non-greedy.
    for m in RULE_RE.finditer(text):
        selector_raw = m.group(1)
        body = m.group(2)
        body_no_comments = _strip_comments(body)
        if not STICKY_RE.search(body_no_comments):
            continue
        if not OVERFLOW_Y_CLIP_RE.search(body_no_comments):
            continue
        # Legitimate pattern: internal vertical scroll via overflow-y:auto/scroll
        # paired with overflow-x:hidden — the user can still reach all content.
        if OVERFLOW_Y_SCROLL_RE.search(body_no_comments):
            continue
        if ALLOW_MARKER in body:  # marker may sit inside the body
            continue
        selector = " ".join(selector_raw.split())[:140]
        line_no = text[: m.start()].count("\n") + 1
        findings.append(f"{path.relative_to(REPO_ROOT)}:{line_no}: {selector}")
    return findings


def scan_all() -> list[str]:
    findings: list[str] = []
    for css_dir in CSS_DIRS:
        if not css_dir.exists():
            continue
        for css in css_dir.rglob("*.css"):
            try:
                text = css.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            findings.extend(_scan_css_text(css, text))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any current violation exceeds baseline (zero-tolerance).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite baseline JSON with current count (use only when reducing).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
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
                {"finding_count": total, "baseline": baseline_total, "findings": findings},
                indent=2,
            )
        )
    else:
        print(f"sticky+overflow:hidden scan: {total} violation(s)")
        print(f"baseline: {baseline_total}")
        for f in findings[:30]:
            print(f"  {f}")

    if args.strict and total > baseline_total:
        print(f"FAIL: {total} > baseline {baseline_total}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
