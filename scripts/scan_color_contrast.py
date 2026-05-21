"""Scan: detect known low-contrast color literal pairs in CSS rule bodies.

This is a *narrow* WCAG 2.1 AA contrast drift detector — it does NOT replace
real automated audits (axe-core, Lighthouse, etc.) that compute contrast in a
live browser with full cascade resolution. Instead, it catches the specific
class of bug that bit the platform multiple times in 2025-2026: a single CSS
rule that hardcodes BOTH a `color:` AND a `background-color:` literal that
happen to fall below the 4.5:1 WCAG AA threshold for normal text.

The bug shape (caught in v3.7.x dark-mode burndown and v3.23.x theme-locked
token sweeps):

    .X {
        color: #888;                ← AAA-fail on white (~3.5:1)
        background-color: #fff;     ← rule renders the same regardless of
    }                                  theme, so dark-mode flip can't save it

Scanner contract:
  * Walks every CSS rule block in `static/css/` and `static/marketing/css/`.
  * Extracts the FIRST `color:` literal and FIRST `background-color:` literal
    in the rule body (literals only — `var(...)` values are skipped because
    they cascade theme-aware).
  * Computes WCAG 2.1 contrast ratio using sRGB → linear-light → relative
    luminance per https://www.w3.org/TR/WCAG21/#dfn-relative-luminance.
  * Flags any pair whose ratio is < 4.5:1 (AA normal text).
  * Honors `/* color-contrast-allow: <reason> */` markers on the rule body
    for intentional decorative low-contrast (e.g. ghost placeholder, watermark).

Zero-tolerance gate from day 1 (v3.57.0, 2026-05-21).

Usage:
    python scripts/scan_color_contrast.py [--strict] [--json] [--update-baseline]
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
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-color-contrast.json"

WCAG_AA_NORMAL = 4.5

RULE_RE = re.compile(r"([^{}@]+)\{([^{}]*)\}", re.DOTALL)
COLOR_RE = re.compile(
    r"(?<!-)color\s*:\s*(#[0-9a-fA-F]{3,8}|rgb\([^)]+\)|rgba\([^)]+\))"
)
BG_RE = re.compile(
    r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,8}|rgb\([^)]+\)|rgba\([^)]+\))"
)
ALLOW_MARKER = "color-contrast-allow:"


def _strip_comments(text: str) -> str:
    return re.sub(
        r"/\*(?!.*" + re.escape(ALLOW_MARKER) + r").*?\*/",
        "",
        text,
        flags=re.DOTALL,
    )


def _parse_color(token: str) -> tuple[int, int, int] | None:
    """Parse a #rgb/#rrggbb/#rrggbbaa/rgb()/rgba() literal to (r,g,b) ints 0-255.

    Returns None when the alpha is < 1 (transparent text/bg can't be reliably
    contrast-checked without knowing what sits behind), or on parse error.
    """
    t = token.strip()
    if t.startswith("#"):
        h = t[1:]
        if len(h) == 3:
            r, g, b = h[0] * 2, h[1] * 2, h[2] * 2
            return int(r, 16), int(g, 16), int(b, 16)
        if len(h) == 4:
            # #rgba — drop check if alpha < 1
            a = int(h[3] * 2, 16)
            if a < 255:
                return None
            return int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16)
        if len(h) == 6:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        if len(h) == 8:
            if int(h[6:8], 16) < 255:
                return None
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return None
    inner = t[t.index("(") + 1 : t.rindex(")")]
    parts = [p.strip() for p in inner.split(",")]
    if len(parts) < 3:
        return None
    try:
        r = _channel(parts[0])
        g = _channel(parts[1])
        b = _channel(parts[2])
    except (ValueError, IndexError):
        return None
    if len(parts) == 4:
        try:
            alpha = float(parts[3])
            if alpha < 1.0:
                return None
        except ValueError:
            return None
    return r, g, b


def _channel(s: str) -> int:
    s = s.strip()
    if s.endswith("%"):
        return round(float(s[:-1]) * 255 / 100)
    return max(0, min(255, int(round(float(s)))))


def _luminance(rgb: tuple[int, int, int]) -> float:
    def _lin(c: int) -> float:
        cs = c / 255.0
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4

    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la = _luminance(a)
    lb = _luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _scan_css_text(path: pathlib.Path, text: str) -> list[str]:
    findings: list[str] = []
    for m in RULE_RE.finditer(text):
        selector_raw = m.group(1)
        body = m.group(2)
        if ALLOW_MARKER in body:
            continue
        body_no_comments = _strip_comments(body)

        c_match = COLOR_RE.search(body_no_comments)
        bg_match = BG_RE.search(body_no_comments)
        if not c_match or not bg_match:
            continue

        fg = _parse_color(c_match.group(1))
        bg = _parse_color(bg_match.group(1))
        if fg is None or bg is None:
            continue

        ratio = _contrast(fg, bg)
        if ratio >= WCAG_AA_NORMAL:
            continue

        selector = " ".join(selector_raw.split())[:120]
        line_no = text[: m.start()].count("\n") + 1
        findings.append(
            f"{path.relative_to(REPO_ROOT)}:{line_no}: {selector} "
            f"(ratio={ratio:.2f} fg={c_match.group(1)} bg={bg_match.group(1)})"
        )
    return findings


def scan_all() -> list[str]:
    findings: list[str] = []
    for css_dir in CSS_DIRS:
        if not css_dir.exists():
            continue
        for css in css_dir.rglob("*.css"):
            # Skip generated/minified bundles — they're build artifacts whose
            # source is in their non-minified twin (already scanned above).
            if css.name.endswith(".min.css"):
                continue
            try:
                text = css.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            findings.extend(_scan_css_text(css, text))
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
                {"finding_count": total, "baseline": baseline_total, "findings": findings},
                indent=2,
            )
        )
    else:
        print(f"color-contrast (WCAG AA normal-text) scan: {total} violation(s)")
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
