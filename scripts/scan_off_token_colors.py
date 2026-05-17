"""Scan CSS files for color declarations that bypass the design-tokens cascade.

A color is OK when:
    * It uses ``var(--token)`` — adapts to light/dark/system automatically
    * It sits inside a theme-definition block (``:root``, ``[data-theme=...]``,
      ``[data-bs-theme=...]``, ``[data-rmc-aesthetic=...]``, or an
      ``@media (prefers-color-scheme: dark)`` group)
    * It's a known-safe literal like ``transparent`` or ``currentColor``
    * The line carries the opt-out marker ``/* off-token-allow: <reason> */``

A color is flagged when a CSS declaration of ``color`` / ``background`` /
``background-color`` / ``border*-color`` / ``outline-color`` / ``fill`` /
``stroke`` sits outside a theme block and contains a hex/rgb literal.

The output is a JSON baseline at
``var/security-audit-baseline-off-token-colors.json`` so CI can fail when
NEW violations land. Existing violations are tracked, not auto-fixed —
the burndown is a separate operator wave.

Usage:
    python scripts/scan_off_token_colors.py [--strict]
        --strict: exit 1 if any current count exceeds the baseline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = [
    ROOT / "static" / "css",
    ROOT / "static" / "marketing" / "css",
]
SKIP_FILES = {"design-tokens.css"}

BASELINE_PATH = ROOT / "var" / "security-audit-baseline-off-token-colors.json"

_HEX_RGB = re.compile(r"(?<!var\(--)(?<!--)(#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\))")
# Only declarations that visibly affect contrast — exclude shadows and gradients
# (which are intentionally fixed colors regardless of theme). Color/background/
# border-color are the ones that flip visibility when the theme changes.
_COLOR_DECL = re.compile(
    r"(color|background(?:-color)?|border(?:-color|-top-color|-bottom-color|-left-color|-right-color)?|outline-color|fill|stroke)\s*:\s*([^;]+);",
    re.IGNORECASE,
)
# Allowlist of value-level patterns that are conventionally fixed-color even
# in tokenized stylesheets (no theme switching expected for these).
_KNOWN_SAFE_LITERALS = (
    "transparent", "currentcolor", "inherit", "initial", "unset",
)
_THEME_BLOCK = re.compile(
    r"(:root\b|\[data-(?:bs-)?theme[^\]]*\]|\[data-rmc-[^\]]*\]|@media\s*\(\s*prefers-color-scheme)",
    re.IGNORECASE,
)
_ALLOW_MARKER = re.compile(r"/\*\s*off-token-allow:[^*]+\*/")


def _strip_comments_preserve_allow(text: str) -> str:
    """Strip CSS comments EXCEPT off-token-allow markers (preserved as opaque tokens)."""
    def _sub(m: re.Match) -> str:
        body = m.group(0)
        if _ALLOW_MARKER.search(body):
            return body  # preserve allow markers so the scanner can see them
        return ""
    return re.sub(r"/\*.*?\*/", _sub, text, flags=re.DOTALL)


def scan_file(path: Path) -> int:
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = _strip_comments_preserve_allow(raw)
    count = 0
    pos = 0
    stack_is_theme: list[bool] = [False]
    while pos < len(text):
        next_open = text.find("{", pos)
        next_close = text.find("}", pos)
        if next_open == -1 and next_close == -1:
            break
        if next_open != -1 and (next_close == -1 or next_open < next_close):
            sel = text[pos:next_open]
            stack_is_theme.append(bool(_THEME_BLOCK.search(sel)) or stack_is_theme[-1])
            pos = next_open + 1
        else:
            body = text[pos:next_close]
            in_theme = stack_is_theme[-1] if stack_is_theme else False
            if not in_theme:
                for m in _COLOR_DECL.finditer(body):
                    if "var(--" in m.group(2):
                        continue
                    # Allow markers can be inside the value OR on the same line
                    # after the semicolon. Walk a bit past the match end.
                    nearby = body[max(0, m.start() - 200):min(len(body), m.end() + 200)]
                    if _ALLOW_MARKER.search(nearby):
                        # Only honor when the marker sits on the same declaration line.
                        line_start = body.rfind("\n", 0, m.start()) + 1
                        line_end = body.find("\n", m.end())
                        if line_end == -1:
                            line_end = len(body)
                        same_line = body[line_start:line_end]
                        if _ALLOW_MARKER.search(same_line):
                            continue
                    if _HEX_RGB.search(m.group(2)):
                        count += 1
            if stack_is_theme:
                stack_is_theme.pop()
            pos = next_close + 1
    return count


def scan_all() -> dict[str, int]:
    findings: dict[str, int] = {}
    for d in SEARCH_DIRS:
        if not d.exists():
            continue
        for f in d.rglob("*.css"):
            if f.name in SKIP_FILES:
                continue
            n = scan_file(f)
            if n:
                findings[str(f.relative_to(ROOT)).replace("\\", "/")] = n
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true",
                         help="Exit 1 if current count exceeds baseline.")
    parser.add_argument("--update-baseline", action="store_true",
                         help="Overwrite baseline JSON with current count (use only when reducing).")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()

    findings = scan_all()
    total = sum(findings.values())

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    baseline = {}
    if BASELINE_PATH.exists():
        try:
            baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            baseline = {}
    baseline_total = int(baseline.get("finding_count", 0))

    if args.update_baseline or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(
            json.dumps(
                {"finding_count": total, "by_file": findings},
                indent=2,
            ),
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps({"finding_count": total, "baseline": baseline_total,
                          "by_file": findings}, indent=2))
    else:
        print(f"off-token color scan: {total} violation(s) across {len(findings)} file(s)")
        print(f"baseline: {baseline_total}")
        if findings:
            print("Top offenders:")
            for f, n in sorted(findings.items(), key=lambda x: -x[1])[:20]:
                print(f"  {n:4}  {f}")

    if args.strict and total > baseline_total:
        print(f"FAIL: {total} > baseline {baseline_total}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
