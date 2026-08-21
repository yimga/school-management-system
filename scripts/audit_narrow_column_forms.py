"""REPORT (not a gate): a form rendered in a grid column that cannot grow.

The Sync Center's rule editor — nine controls — rendered inside `.rmc-sc-sched`'s
`minmax(0, 1fr) 15rem` aside. At 240px the mode select truncated mid-word, a label wrapped
away from its control, and a seven-chip day picker broke six-and-one. None of that is a
styling bug; it is a form in a column sized for a list, and no media query rescues it
because the track is 240px on a 27" display too.

This finds other instances. It always exits 0. Do not wire it into CI.

WHAT COUNTS AS NARROW
  Only a track that CANNOT grow: a bare `15rem`/`240px`, or `minmax(len, len)` with two
  fixed ends. `minmax(16rem, 0.62fr)` has a FLOOR of 16rem and grows from there, so it is
  not a finding — an earlier version counted it and buried the signal.

WHAT IT GETS WRONG — read before acting on a row
  * Which grid CHILD the form lands in is not decidable statically. A row means "this
    template renders a form, and uses a class whose grid has a rigid narrow track" — not
    that the form is in that track. Open the template.
  * Narrow tracks are usually CORRECT. A 1–3rem rigid track is an icon, checkbox or badge
    gutter. On 2026-08-21 this reported 12 pairs and every one except `.rmc-sc-sched` was
    a gutter of 1–2.9rem doing exactly its job.
  * Only bespoke prefixed classes are considered. A grid keyed on `.row` or `.d-flex`
    says nothing about which rule applies to a given template.

Stdlib only.
"""
from __future__ import annotations

import argparse
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
CSS_DIRS = [REPO / "static" / "css", REPO / "static" / "marketing" / "css"]
TEMPLATE_DIR = REPO / "templates"

#: A form needs more than this to lay out; a list of names does not.
NARROW_REM = 17.0
MIN_CONTROLS = 3

_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
_GTC = re.compile(r"grid-template-columns\s*:\s*([^;]+);")
_CLASS = re.compile(r"\.([a-zA-Z][\w-]*)")
_BESPOKE = re.compile(r"^(rmc|cp|mkt|portal|sc|ds|admin|dash|setup|wiz|hub)[-_]")
_CONTROL = re.compile(r"<(input|select|textarea)\b|\{\{\s*form\.\w+\s*\}\}", re.I)


def _split_tracks(decl: str) -> list[str]:
    """Split a track list on top-level whitespace, keeping minmax(...) intact."""
    out, depth, current = [], 0, ""
    for ch in decl:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth == 0:
            if current:
                out.append(current)
                current = ""
            continue
        current += ch
    if current:
        out.append(current)
    return out


def _to_rem(value: str) -> float | None:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)rem", value)
    if m:
        return float(m.group(1))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)px", value)
    if m:
        return float(m.group(1)) / 16
    return None


def _rigid_width(track: str) -> float | None:
    """Width in rem if the track cannot grow, else None."""
    t = track.strip().lower()
    m = re.fullmatch(r"minmax\(\s*([^,]+),\s*([^)]+)\)", t)
    if m:
        upper = m.group(2).strip()
        if "fr" in upper or "%" in upper or upper in ("auto", "max-content", "min-content"):
            return None
        return _to_rem(upper)
    if "fr" in t or "%" in t or t in ("auto", "max-content", "min-content"):
        return None
    return _to_rem(t)


def _css_files():
    out = []
    for directory in CSS_DIRS:
        if directory.is_dir():
            out += [
                p for p in sorted(directory.glob("*.css"))
                if not p.name.endswith(".min.css")
            ]
    return out


def rigid_grids() -> dict:
    """Bespoke class -> (stylesheet, declaration, narrowest rigid track in rem)."""
    grids = {}
    for path in _css_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        for match in _RULE.finditer(text):
            selectors, body = match.group(1), match.group(2)
            found = _GTC.search(body)
            if not found:
                continue
            decl = " ".join(found.group(1).split())
            if "auto-fit" in decl or "auto-fill" in decl or "repeat(" in decl:
                continue  # responsive by construction
            tracks = _split_tracks(decl)
            if len(tracks) < 2:
                continue
            rigid = [w for w in (_rigid_width(t) for t in tracks) if w is not None]
            if not rigid or not any("fr" in t for t in tracks):
                continue
            narrowest = min(rigid)
            if narrowest > NARROW_REM:
                continue
            for cls in set(_CLASS.findall(selectors)):
                if _BESPOKE.match(cls):
                    grids.setdefault(cls, (path.name, decl, narrowest))
    return grids


def audit():
    grids = rigid_grids()
    hits = []
    if not TEMPLATE_DIR.is_dir():
        return grids, hits
    for template in sorted(TEMPLATE_DIR.rglob("*.html")):
        try:
            src = template.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "<form" not in src.lower():
            continue
        controls = len(_CONTROL.findall(src))
        if controls < MIN_CONTROLS:
            continue
        for cls, (stylesheet, decl, width) in grids.items():
            if re.search(r'class="[^"]*\b' + re.escape(cls) + r'\b', src):
                hits.append((
                    controls, width, template.relative_to(REPO).as_posix(),
                    cls, stylesheet, decl,
                ))
    hits.sort(reverse=True)
    return grids, hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Forms in columns that cannot grow.")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    grids, hits = audit()
    print(f"grids with a track that cannot grow and is <= {NARROW_REM}rem: {len(grids)}")
    print()
    print(f"{'ctrls':>5}  {'track':>7}  template / grid class")
    print("-" * 92)
    for controls, width, template, cls, stylesheet, decl in hits[: args.limit]:
        print(f"{controls:>5}  {width:>6.1f}r  {template}")
        print(f"                 .{cls}  ({stylesheet})  ->  {decl[:66]}")
    print()
    print(f"candidate template/grid pairs: {len(hits)}")
    print("Report only — a rigid track under ~3rem is almost always a correct gutter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
