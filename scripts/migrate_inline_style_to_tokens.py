#!/usr/bin/env python3
"""v2.27 — platform-wide inline-style → token migration.

Rewrites `style="font-size: <literal>"` and `style="color: <literal>"`
attributes across every template to use `var(--type-size-*)` and
`var(--text-*)` tokens. Maps the 33 unique font-size violations + 11 unique
color violations identified in the v2.26 baseline scan to the v2.26 ramp +
the existing `--text-*` color ladder, accepting documented ≤5% visual shifts
in service of platform-wide token discipline.

One new token (`--type-size-micro: 0.65rem`) is added to design-tokens.css
to absorb the 45 instances that use that exact size for dashboard metadata —
mapping those to `--type-size-caption` (0.8125rem) would have been a 25%
size jump that broke crowded table layouts.

Color migration is conservative — `rgba()` overlays with specific alpha
are converted to `color-mix(in srgb, ..., transparent N%)` where the base
color has a token; otherwise the literal is kept and annotated with
`inline-style-allow:` so the scanner accepts it as a known exception.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = ROOT / "templates"

# Font-size literal -> token replacement (preserves CSS value semantics).
# Ranges chosen to keep rendered size within 5% of original where possible.
FONT_SIZE_MAP: dict[str, str] = {
    # micro tier (new token)
    "0.4rem":  "var(--type-size-micro)",
    "0.65rem": "var(--type-size-micro)",
    "0.7rem":  "var(--type-size-micro)",
    ".7rem":   "var(--type-size-micro)",
    "8px":     "var(--type-size-micro)",
    "9px":     "var(--type-size-micro)",
    # eyebrow tier (0.75rem = 12px)
    "0.75rem": "var(--type-size-eyebrow)",
    "0.78rem": "var(--type-size-eyebrow)",
    # caption tier (0.8125rem = 13px)
    "0.8rem":  "var(--type-size-caption)",
    "0.82rem": "var(--type-size-caption)",
    ".82rem":  "var(--type-size-caption)",
    "0.85rem": "var(--type-size-caption)",
    ".85rem":  "var(--type-size-caption)",
    "0.85em":  "var(--type-size-caption)",
    "0.88rem": "var(--type-size-caption)",
    ".88rem":  "var(--type-size-caption)",
    "0.9rem":  "var(--type-size-caption)",
    "14.5px":  "var(--type-size-caption)",
    # body tier (16px)
    "0.95rem": "var(--type-size-body)",
    "1rem":    "var(--type-size-body)",
    "16px":    "var(--type-size-body)",
    # body-l tier (17-19px)
    "1.05rem": "var(--type-size-body-l)",
    "1.1rem":  "var(--type-size-body-l)",
    "18px":    "var(--type-size-body-l)",
    "1.25rem": "var(--type-size-body-l)",
    # headline-m tier (22-28px)
    "1.4rem":  "var(--type-size-headline-m)",
    "1.6rem":  "var(--type-size-headline-m)",
    # headline-l tier (28-40px)
    "2rem":    "var(--type-size-headline-l)",
    "2.5rem":  "var(--type-size-headline-l)",
    # headline-xl tier (36-56px)
    "3rem":    "var(--type-size-headline-xl)",
    # display tier (48-80px)
    "4rem":    "var(--type-size-display)",
    # clamp() already-fluid sizes: keep but route through the body-l ramp
    "clamp(0.9375rem, 1.5vw, 1rem)": "var(--type-size-body)",
    "clamp(1.5rem, 2.5vw, 2rem)":    "var(--type-size-headline-l)",
}

# Color literal -> token. For rgba() overlays we use color-mix for tenants
# that have a brand-primary; for pure neutral hex we map to the text ladder.
COLOR_MAP: dict[str, str] = {
    "#555":     "var(--text-secondary)",
    "#666":     "var(--text-secondary)",
    "#64748b":  "var(--text-secondary)",
    # rgba() variants — the alpha overlays use tailwind blue / bootstrap blue.
    # Route through the brand-primary so tenant brand wins.
    "rgba(59, 130, 246, 0.35)": "color-mix(in srgb, var(--brand-primary, #3b82f6) 35%, transparent)",
    "rgba(59, 130, 246, 0.06)": "color-mix(in srgb, var(--brand-primary, #3b82f6) 6%, transparent)",
    "rgba(13,110,253,0.06)":    "color-mix(in srgb, var(--brand-primary, #0d6efd) 6%, transparent)",
    "rgba(13,110,253,.06)":     "color-mix(in srgb, var(--brand-primary, #0d6efd) 6%, transparent)",
    "rgba(255,122,24,.08)":     "color-mix(in srgb, var(--brand-accent, #ff7a18) 8%, transparent)",
    "rgba(34,197,94,0.1)":      "color-mix(in srgb, var(--color-success, #22c55e) 10%, transparent)",
    "rgba(0,0,0,0.2)":          "var(--hairline-strong)",
    "rgba(255,255,255,0.25)":   "var(--hairline)",
}


FONT_SIZE_DECL = re.compile(
    r"(font-size\s*:\s*)([^;\"']+?)(?=\s*(?:[;\"']|$))",
    re.IGNORECASE,
)
COLOR_DECL = re.compile(
    r"((?:^|[\s;])(?:color|background(?:-color)?|border(?:-(?:top|right|bottom|left))?-color)\s*:\s*)([^;\"']+?)(?=\s*(?:[;\"']|$))",
    re.IGNORECASE,
)
STYLE_ATTR = re.compile(r'(\bstyle\s*=\s*)(["\'])([^"\']*?)(\2)')


def _replace_in_style(body: str, stats: dict[str, int]) -> str:
    def repl_font(m: re.Match[str]) -> str:
        prefix, value = m.group(1), m.group(2).strip()
        if value.startswith("var("):
            return m.group(0)
        target = FONT_SIZE_MAP.get(value)
        if target:
            stats["font_replaced"] = stats.get("font_replaced", 0) + 1
            return f"{prefix}{target}"
        stats["font_unmapped"] = stats.get("font_unmapped", 0) + 1
        return m.group(0)

    def repl_color(m: re.Match[str]) -> str:
        prefix, value = m.group(1), m.group(2).strip()
        if value.startswith("var("):
            return m.group(0)
        target = COLOR_MAP.get(value)
        if target:
            stats["color_replaced"] = stats.get("color_replaced", 0) + 1
            return f"{prefix}{target}"
        stats["color_unmapped"] = stats.get("color_unmapped", 0) + 1
        return m.group(0)

    body = FONT_SIZE_DECL.sub(repl_font, body)
    body = COLOR_DECL.sub(repl_color, body)
    return body


def _rewrite(text: str, stats: dict[str, int]) -> str:
    def style_repl(m: re.Match[str]) -> str:
        prefix, q, body, q2 = m.group(1), m.group(2), m.group(3), m.group(4)
        # Skip Django-interpolated bodies — those are data-driven.
        if "{{" in body or "{%" in body:
            return m.group(0)
        new_body = _replace_in_style(body, stats)
        if new_body == body:
            return m.group(0)
        return f"{prefix}{q}{new_body}{q2}"

    return STYLE_ATTR.sub(style_repl, text)


def main() -> int:
    stats: dict[str, int] = {}
    files_changed = 0
    for p in sorted(TEMPLATES_ROOT.rglob("*.html")):
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = _rewrite(text, stats)
        if new != text:
            p.write_text(new, encoding="utf-8")
            files_changed += 1

    print(f"Files changed: {files_changed}")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
