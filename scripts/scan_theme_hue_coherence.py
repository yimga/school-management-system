"""A theme must sit in ONE hue family. Ground, surfaces, text and masthead all agree.

WHAT THIS CATCHES, AND HOW IT GOT HERE. The `ink` backend theme shipped a slate-950
body (#030712 — blue-black) over the surface pair #1a1612 / #241e18, which is the WARM
brown ramp belonging to `steel`, whose own BODY is #241e18. `midnight` carried the
identical pair. So on those two themes every card, alert, dropdown, striped table row and
form control rendered brown inside a navy shell — and because `backend-themes.css` sets
those with `!important` on bare `input`, `select` and `textarea`, no page could opt out
and no page could be blamed. It surfaced on the densest form the platform has, the sync
schedule rule editor, where a dozen small brown controls sit on a navy card; but the
defect was never that page's, and fixing it there would have fixed one screen out of
every screen those two themes touch.

WHY A HUE TEST RATHER THAN A CONTRAST TEST. Contrast was never the problem: the warm
pair measured 6.95:1 for muted text, which passes AA comfortably, so every accessibility
gate the repo already runs was green while the page looked wrong. What was wrong is that
two colours in the same visual stack disagreed about which direction "neutral" was. That
is a hue question, and nothing here asked it.

HOW IT DECIDES. For each theme block: take the ground (`background`), the surface ramp
(`--backend-surface`, `--backend-surface-alt`), the text pair and every stop of the
masthead gradient. Convert to HSV hue. Colours whose chroma is at or below
NEUTRAL_CHROMA are achromatic — a grey has no hue to disagree with — and are skipped, so
a fully neutral theme like `onyx` is coherent by construction. Of the rest, the widest
CIRCULAR distance between any two hues must stay within HUE_SPREAD_LIMIT. Warm-on-warm
and cool-on-cool pass; a 166° spread between #241e18 (30°, orange) and #030712 (224°,
blue) does not.

Deliberately biased toward false NEGATIVES: only hex literals are read. A theme built
from `color-mix()` or a var() chain is skipped rather than guessed at, because a gate
that cries wolf about a palette it cannot actually see is a gate people switch off.

Mark a reviewed, deliberate two-hue theme with `/* theme-hue-allow: <reason> */` inside
the block.

Stdlib only — this runs as a deps-free boundary job.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
CSS_DIR = REPO / "static" / "css"
BASELINE = REPO / "var" / "security-audit-baseline-theme-hue-coherence.json"
ALLOW_MARKER = "theme-hue-allow:"

#: Chroma (max channel - min channel, 0-255) at or below which a colour is a grey and
#: therefore has no hue to disagree with. 6 keeps #f8fafc (4) and #18181b (3) neutral
#: while leaving #030712 (15) and #fffaf0 (15) as real, directional colours.
NEUTRAL_CHROMA = 6

#: Widest circular hue spread, in degrees, allowed inside one theme. 60 is a whole
#: primary-to-primary step: it passes a ramp that drifts as it lightens (ocean spans 17°,
#: amber 18°) and fails a ramp assembled from two different palettes (ink spanned 166°).
HUE_SPREAD_LIMIT = 60

#: The declarations that make up a theme's visual stack.
_COLOR_PROPS = (
    "background",
    "--backend-surface",
    "--backend-surface-alt",
    "--backend-text",
    "--backend-text-muted",
    "--header-brand-bg",
    "--header-brand-fg",
)

_THEME_BLOCK = re.compile(r"body\.portal-backend-([a-z0-9-]+)\s*\{(.*?)\}", re.S)
_HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")


def _rgb(token: str) -> tuple[int, int, int]:
    h = token.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _chroma(rgb: tuple[int, int, int]) -> int:
    return max(rgb) - min(rgb)


def _hue(rgb: tuple[int, int, int]) -> float:
    """HSV hue in degrees. Undefined for greys; callers filter on chroma first."""
    r, g, b = rgb
    hi, lo = max(rgb), min(rgb)
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


def _widest_spread(hues: list[float]) -> tuple[float, float, float]:
    """Widest circular gap between any two hues, with the offending pair."""
    worst = (0.0, 0.0, 0.0)
    for i, first in enumerate(hues):
        for second in hues[i + 1 :]:
            gap = _circular_gap(first, second)
            if gap > worst[0]:
                worst = (gap, first, second)
    return worst


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _css_files() -> list[pathlib.Path]:
    if not CSS_DIR.is_dir():
        return []
    return sorted(p for p in CSS_DIR.glob("*.css") if not p.name.endswith(".min.css"))


def scan_text(rel: str, text: str) -> list[dict]:
    """Findings for one stylesheet's source. The unit the tests drive."""
    findings: list[dict] = []
    for match in _THEME_BLOCK.finditer(text):
        name, body = match.group(1), match.group(2)
        if "--backend-surface" not in body:
            # Not a theme DEFINITION block — just a rule scoped to the theme.
            continue
        if ALLOW_MARKER in body:
            continue

        samples: list[tuple[str, str, float]] = []
        for prop in _COLOR_PROPS:
            for decl in re.finditer(re.escape(prop) + r"\s*:\s*([^;]+);", body):
                for hex_match in _HEX.finditer(decl.group(1)):
                    rgb = _rgb(hex_match.group(0))
                    if _chroma(rgb) <= NEUTRAL_CHROMA:
                        continue
                    samples.append((prop, hex_match.group(0), _hue(rgb)))

        if len(samples) < 2:
            continue
        spread, lo_hue, hi_hue = _widest_spread([s[2] for s in samples])
        if spread <= HUE_SPREAD_LIMIT:
            continue

        def _named(target: float) -> str:
            for prop, token, hue in samples:
                if abs(hue - target) < 1e-9:
                    return f"{prop} {token} ({hue:.0f}deg)"
            return f"{target:.0f}deg"

        findings.append(
            {
                "path": rel,
                "line": _line_of(text, match.start()),
                "theme": name,
                "spread_degrees": round(spread),
                "detail": (
                    f"theme '{name}' spans {spread:.0f}deg of hue: "
                    f"{_named(lo_hue)} vs {_named(hi_hue)}"
                ),
            }
        )
    return findings


def scan() -> list[dict]:
    findings: list[dict] = []
    for path in _css_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # An unreadable stylesheet is not this gate's finding to report.
            continue
        findings.extend(scan_text(path.relative_to(REPO).as_posix(), text))
    return findings


def _payload(findings: list[dict]) -> dict:
    return {"finding_count": len(findings), "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 on any finding")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings = scan()

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(_payload(findings), indent=2) + "\n", encoding="utf-8"
        )
        print(f"baseline written: {len(findings)} finding(s)")
        return 0

    if args.json:
        print(json.dumps(_payload(findings), indent=2, sort_keys=True))
        return 1 if findings and args.strict else 0

    if not findings:
        print(
            "theme hue coherence: 0 violation(s) — every theme's ground, surfaces, "
            "text and masthead sit in one hue family"
        )
        return 0

    print(f"theme hue coherence: {len(findings)} violation(s)", file=sys.stderr)
    for f in findings:
        print(f"  {f['path']}:{f['line']}  {f['detail']}", file=sys.stderr)
    print(
        "\nA surface ramp borrowed from another palette renders the wrong hue on every "
        "card, alert, dropdown and form control the theme touches, and contrast gates "
        "will not see it. Re-derive the ramp from the theme's own ground, or mark a "
        f"deliberate two-hue theme '{ALLOW_MARKER} <reason>'.",
        file=sys.stderr,
    )
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
