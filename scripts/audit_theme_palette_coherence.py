"""REPORT (not a gate): every palette-defining CSS block, checked for a borrowed ramp.

This is the wide-angle companion to `scan_theme_hue_coherence.py`. That gate is
zero-tolerance and therefore deliberately narrow — it only reads `body.portal-backend-*`
theme blocks, where "one theme, one hue family" is an unambiguous contract. This script
asks the same question of EVERY palette block on the platform, accepts that some of its
answers are wrong, and prints them for a person to judge.

It is what found `rmc-premium-os.css`, `backend-light-theme.css` and
`tokens-schoolhouse.css` on 2026-08-21. It always exits 0. Do not wire it into CI.

WHAT IT ASKS
  1. RAMP HUE COHERENCE — do a block's ground+surface tokens agree with each other?
     Do its text tokens agree with each other? The `ink`/`midnight` defect was a navy
     ground under a surface ramp copied from `steel`: elements of the SAME ROLE
     disagreeing about which direction neutral is.
  2. SAME-BLOCK CONTRAST — a block defining both a text token and a surface token is
     asserting they get used together; if that pairing fails AA it ships its own
     unreadable combination.

WHAT IT GETS WRONG — read before acting on a row
  * CROSS-ROLE hue difference is NOT checked, on purpose. A cool ground under warm text
    (`#0C1422` navy, `#F5F1EA` ivory) is the marketing editorial identity, chosen
    deliberately. An earlier version compared across roles and returned ~31 rows that
    were almost all good design.
  * Paired-variant tokens still trip check 1. `--mkt-ink-inv` is the INVERTED text made
    for `--mkt-surface-deep`; naming cannot tell the script they belong together, so the
    schoolhouse editorial block reports and should be ignored.
  * Check 2 cross-products every text token against every surface token in the block.
    In a large `:root` that is mostly meaningless — `--admin-sidebar-logo-fg` does not
    sit on `--surface-elevated`. Before believing a contrast row, find the rule that
    actually pairs them. On 2026-08-21 four backend-theme rows looked like AA failures
    until the cards were found to use `--backend-surface`, not `--backend-surface-alt`;
    against the real surface all 12 themes passed.
  * Only the FIRST hex in a declaration is read, so `var(--x, #fallback)` reports the
    FALLBACK, not the operative value.

Stdlib only.
"""
from __future__ import annotations

import argparse
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
CSS_DIRS = [REPO / "static" / "css", REPO / "static" / "marketing" / "css"]

SURFACE_PROPS = re.compile(
    r"--(?:[a-z0-9-]*-)?(?:surface|canvas|bg|background|elevated|sunken|popover|paper|card)"
    r"(?:-[a-z0-9-]+)?$"
)
TEXT_PROPS = re.compile(
    r"--(?:[a-z0-9-]*-)?(?:text|ink|fg|foreground|muted|subtle)(?:-[a-z0-9-]+)?$"
)

#: Tokens whose whole job is to differ in hue from the neutral ramp. Including them
#: guarantees a finding on every well-built palette, which is how a report becomes noise.
SEMANTIC = re.compile(
    r"warning|danger|error|success|alert|status|critical|info|positive|negative|"
    r"accent|brand|primary|secondary|graph|chart|badge|pill|tint|highlight|focus|link|"
    r"gradient|glow|shadow|overlay|scrim|selection|hover|active|disabled"
)

_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
_DECL = re.compile(r"(--[a-z0-9-]+|background(?:-color)?|color)\s*:\s*([^;]+);")
_HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")

NEUTRAL_CHROMA = 6
HUE_SPREAD_LIMIT = 60
AA = 4.5


def _rgb(token: str) -> tuple[int, int, int]:
    h = token.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _chroma(c) -> int:
    return max(c) - min(c)


def _hue(c) -> float:
    r, g, b = c
    hi, lo = max(c), min(c)
    span = hi - lo
    if span == 0:
        return 0.0
    if hi == r:
        h = ((g - b) / span) % 6
    elif hi == g:
        h = (b - r) / span + 2
    else:
        h = (r - g) / span + 4
    return (h * 60) % 360


def _circular_gap(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _relative_luminance(c) -> float:
    def channel(v: int) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _widest(group):
    chromatic = [(p, t, _hue(c)) for p, t, c in group if _chroma(c) > NEUTRAL_CHROMA]
    worst = (0.0, None, None)
    for i, first in enumerate(chromatic):
        for second in chromatic[i + 1:]:
            g = _circular_gap(first[2], second[2])
            if g > worst[0]:
                worst = (g, first, second)
    return worst


def _css_files():
    out = []
    for directory in CSS_DIRS:
        if directory.is_dir():
            out += [
                p for p in sorted(directory.glob("*.css"))
                if not p.name.endswith(".min.css")
            ]
    return out


def audit():
    ramp, contrast = [], []
    for path in _css_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(REPO).as_posix()
        # Strip comments first, so prose or an allow-marker never reads as a declaration.
        stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        for match in _RULE.finditer(stripped):
            selector = " ".join(match.group(1).split())[:88]
            body = match.group(2)
            surfaces, texts = [], []
            for prop, value in _DECL.findall(body):
                if SEMANTIC.search(prop):
                    continue
                hexes = _HEX.findall(value)
                if not hexes:
                    continue
                token = "#" + hexes[0]
                colour = _rgb(token)
                if prop in ("background", "background-color") or SURFACE_PROPS.match(prop):
                    surfaces.append((prop, token, colour))
                elif prop == "color" or TEXT_PROPS.match(prop):
                    texts.append((prop, token, colour))

            for label, group in (("surface ramp", surfaces), ("text ramp", texts)):
                if len(group) < 2:
                    continue
                spread, a, b = _widest(group)
                if spread > HUE_SPREAD_LIMIT:
                    ramp.append((
                        round(spread), rel, selector, label,
                        f"{a[0]} {a[1]} ({a[2]:.0f}deg) vs {b[0]} {b[1]} ({b[2]:.0f}deg)",
                    ))

            # Token-vs-token only: a component rule setting both `color` and `background`
            # is often an icon or a mask, where identical values are the point.
            tok_surfaces = [x for x in surfaces if x[0].startswith("--")]
            tok_texts = [x for x in texts if x[0].startswith("--")]
            if tok_surfaces and tok_texts:
                worst, pair = 99.0, None
                for sp, st, sc in tok_surfaces:
                    for tp, tt, tc in tok_texts:
                        ratio = _contrast(sc, tc)
                        if ratio < worst:
                            worst, pair = ratio, (tp, tt, sp, st)
                if worst < AA:
                    contrast.append((
                        round(worst, 2), rel, selector,
                        f"{pair[0]} {pair[1]} on {pair[2]} {pair[3]}",
                    ))

    ramp.sort(reverse=True)
    contrast.sort()
    return ramp, contrast


def main() -> int:
    parser = argparse.ArgumentParser(description="Platform palette coherence report.")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()

    ramp, contrast = audit()

    print("=" * 92)
    print(f"RAMP HUE INCOHERENCE — same-role tokens disagreeing  ({len(ramp)})")
    print("=" * 92)
    for spread, rel, sel, label, detail in ramp[: args.limit]:
        print(f"{spread:>4}deg [{label}]  {rel}")
        print(f"          {sel}")
        print(f"          {detail}")

    print()
    print("=" * 92)
    print(f"SAME-BLOCK CONTRAST BELOW AA  ({len(contrast)})")
    print("=" * 92)
    for ratio, rel, sel, detail in contrast[: args.limit]:
        print(f"{ratio:>6}:1  {rel}")
        print(f"          {sel}")
        print(f"          {detail}")

    print()
    print(f"TOTALS: ramp_hue={len(ramp)}  same_block_contrast={len(contrast)}")
    print("Report only — read the module docstring before acting on a row.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
