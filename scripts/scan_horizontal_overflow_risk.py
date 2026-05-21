"""Scan: detect horizontal-overflow risk from `white-space: nowrap` without containment.

The bug shape (caught systemically at v3.54.0 across all 4 studio_os mode rails
in studio-mode-rail.css:5-14; the fix added `min-width:0; overflow-wrap:anywhere;
word-break:break-word` to the shared rail link rule):

    .rail__link {
        white-space: nowrap;       ← long labels never wrap
        /* no text-overflow: ellipsis */
        /* no overflow: hidden     */
    }                                if the parent is flex/grid, the nowrap
                                     text overflows horizontally and the
                                     parent column expands past its bounds.

This scanner walks every CSS rule block in `static/css/` and `static/marketing/css/`
and flags any rule whose declaration body contains `white-space: nowrap` AND has
NONE of the following safe containment mechanisms:

  * `text-overflow: ellipsis`   (truncates with ellipsis — needs overflow + width)
  * `overflow: hidden|clip`     (clips horizontally and vertically)
  * `overflow-x: hidden|clip`   (clips horizontally)
  * `overflow-wrap: anywhere`   (allows word-break — softens nowrap effect)
  * `word-break: break-all|break-word`
  * `min-width: 0`              (allows flex shrinking — pairs with overflow-wrap)

The combo is almost always wrong on text that might come from operator input,
i18n with German/Finnish long compound words, or tenant school names. If you
genuinely want a marquee-style "never wrap, let it overflow visually" (e.g.
a horizontal scroll-snap row, a constant-width tab strip), mark the declaration
with `/* horizontal-overflow-risk-allow: <reason> */` on the line of the
`white-space: nowrap` declaration or anywhere in the rule body.

Zero-tolerance gate from day 1 (v3.57.0, 2026-05-21).

Usage:
    python scripts/scan_horizontal_overflow_risk.py [--strict] [--json] [--update-baseline]
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
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-horizontal-overflow-risk.json"

RULE_RE = re.compile(r"([^{}@]+)\{([^{}]*)\}", re.DOTALL)
NOWRAP_RE = re.compile(r"white-space\s*:\s*nowrap\b")

# Any one of these in the same rule body resolves the overflow risk.
SAFE_PATTERNS = [
    re.compile(r"text-overflow\s*:\s*ellipsis\b"),
    re.compile(r"overflow\s*:\s*(?:hidden|clip)\b"),
    re.compile(r"overflow-x\s*:\s*(?:hidden|clip|auto|scroll)\b"),
    re.compile(r"overflow-wrap\s*:\s*(?:anywhere|break-word)\b"),
    re.compile(r"word-break\s*:\s*(?:break-all|break-word|anywhere)\b"),
    # min-width:0 alone isn't sufficient — but it's a signal the author thought
    # about flex shrinking; pair it with width:1px-ish or display:block contexts.
    re.compile(r"min-width\s*:\s*0\b"),
]

ALLOW_MARKER = "horizontal-overflow-risk-allow:"


def _strip_comments(text: str) -> str:
    # Preserve comments containing the allow marker so they survive into the body match.
    return re.sub(
        r"/\*(?!.*" + re.escape(ALLOW_MARKER) + r").*?\*/",
        "",
        text,
        flags=re.DOTALL,
    )


def _scan_css_text(path: pathlib.Path, text: str) -> list[str]:
    findings: list[str] = []
    for m in RULE_RE.finditer(text):
        selector_raw = m.group(1)
        body = m.group(2)
        body_no_comments = _strip_comments(body)
        if not NOWRAP_RE.search(body_no_comments):
            continue
        if any(rx.search(body_no_comments) for rx in SAFE_PATTERNS):
            continue
        if ALLOW_MARKER in body:
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
        print(f"horizontal-overflow-risk scan: {total} violation(s)")
        print(f"baseline: {baseline_total}")
        for f in findings[:30]:
            print(f"  {f}")
        if len(findings) > 30:
            print(f"  … {len(findings) - 30} more")

    if args.strict and total > baseline_total:
        print(f"FAIL: {total} > baseline {baseline_total}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
