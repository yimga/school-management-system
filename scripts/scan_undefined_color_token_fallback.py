#!/usr/bin/env python3
"""Scanner: invisible-control / invisible-text collapses from UNDEFINED color tokens.

Both 2026-08-08 visibility waves had the same root cause, a class the literal-pair
`scan_color_contrast.py` is structurally blind to: a `color`/`background`/`border-color`
declaration reads `var(--X, <fallback>)` where **--X is never declared anywhere** in the
CSS layer, so the value silently falls through to the fallback. When the fallback is a
token from the COLLIDING tier the control/text goes invisible:

  * `.rmc-day1-cta-primary { background: var(--accent-primary, var(--text-primary));
     color: var(--surface-bg); }` -- --accent-primary undefined -> bg = --text-primary,
     which on the dark studio canvas flips near-white while --surface-bg stays light ->
     the reported white-on-white "See three palette options" pill.
  * `color: var(--brand-accent-ink, var(--surface-bg))` -- text painted with a surface
     token -> invisible on any matching surface.
  * bare `background: var(--surface-2)` for an undeclared token -> invalid value, the
     declaration is dropped entirely.

This gate collects every declared custom property across the CSS layer, then flags color
declarations whose FIRST `var()` names an undeclared token in one of three high-confidence
collapse shapes:

  (a) BARE undeclared token in any color context           -> property dropped
  (b) `color:` with fallback var() to a SURFACE/BG token    -> text = background
  (c) `background[-color]:` with fallback var() to a TEXT   -> background = text (day1)

Undeclared tokens that fall back to a literal colour (`var(--x, #fff)`) are NOT flagged --
they render the literal, which is a real colour. Mark a reviewed, deliberate site with
`/* undefined-token-allow: <reason> */` on the declaration line or the line above.

Stdlib-only (no Django), so it runs in the deps-free architectural-boundaries job.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CSS_DIRS = [_ROOT / "static" / "css", _ROOT / "static" / "marketing" / "css"]
_TEMPLATE_DIRS = [_ROOT / "templates"]
_JS_DIRS = [_ROOT / "static" / "js"]
_BASELINE = _ROOT / "var" / "security-audit-baseline-undefined-token-fallback.json"

_COLOR_PROPS = (
    "color",
    "background",
    "background-color",
    "border-color",
    "border-top-color",
    "border-bottom-color",
    "border-left-color",
    "border-right-color",
    "outline-color",
    "fill",
    "stroke",
)
_BG_PROPS = {"background", "background-color"}
_TEXT_PROPS = {"color", "fill"}

_DECL_RE = re.compile(r"--([A-Za-z0-9_-]+)\s*:")
_PROP_RE = re.compile(
    r"(?P<prop>" + "|".join(re.escape(p) for p in _COLOR_PROPS) + r")\s*:\s*(?P<value>[^;}{]*)",
    re.IGNORECASE,
)
_ALLOW = "undefined-token-allow"


def _strip_comments_keep_lines(text: str) -> str:
    return re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL)


def _iter_css_files():
    for base in _CSS_DIRS:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.css")):
            yield path


def _first_var(value: str):
    """Return (token_name, fallback_str_or_None) for the FIRST var() in value, else None."""
    idx = value.find("var(")
    if idx == -1:
        return None
    i = idx + len("var(")
    depth = 1
    inner_start = i
    while i < len(value) and depth:
        c = value[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    inner = value[inner_start:i]
    # split on the first TOP-LEVEL comma
    depth = 0
    comma = -1
    for j, c in enumerate(inner):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            comma = j
            break
    if comma == -1:
        name = inner.strip()
        fb = None
    else:
        name = inner[:comma].strip()
        fb = inner[comma + 1 :].strip()
    if not name.startswith("--"):
        return None
    return name, fb


def _tier(name: str) -> str:
    """Classify a token name into 'surface', 'text', or 'other'."""
    n = name
    if (
        n.startswith("--surface-")
        or n.startswith("--bg-")
        or n.startswith("--canvas")
        or n.startswith("--page-bg")
        or n.startswith("--card-bg")
        or n.startswith("--dashboard-card-bg")
        or n.endswith("-bg")
        or n.endswith("-canvas")
        or n in {"--surface", "--canvas", "--body-bg"}
    ):
        return "surface"
    if (
        n in {"--text-primary", "--text-secondary", "--text-tertiary", "--text-muted"}
        or n.startswith("--ink")
        or n.endswith("-ink")
    ):
        return "text"
    return "other"


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _has_marker(original_lines, line_no: int) -> bool:
    for probe in (line_no - 1, line_no - 2):  # 1-indexed; line and line above
        if 0 <= probe < len(original_lines) and _ALLOW in original_lines[probe]:
            return True
    return False


_SETPROP_RE = re.compile(r"""setProperty\(\s*['"]--([A-Za-z0-9_-]+)""")


def collect_declared() -> set:
    """Every custom property DECLARED anywhere it can legitimately be set:
    a `--x:` declaration in a .css file, in a template inline `style="--x:"` /
    `<style>` block, or a JS `setProperty('--x', ...)` (day1 per-card palette,
    reportcard preview, etc. are populated at runtime -- those are declared, not
    missing). Over-collecting is safe: it only makes the gate MORE lenient, never
    flags valid code -- a false-negative bias, never a false-positive one."""
    declared = set()
    for path in _iter_css_files():
        text = _strip_comments_keep_lines(path.read_text(encoding="utf-8", errors="replace"))
        declared.update(_DECL_RE.findall(text))
    for base in _TEMPLATE_DIRS:
        if base.exists():
            for path in base.rglob("*.html"):
                text = path.read_text(encoding="utf-8", errors="replace")
                declared.update(_DECL_RE.findall(text))  # inline style="" + <style> blocks
    for base in _JS_DIRS:
        if base.exists():
            for path in base.rglob("*.js"):
                text = path.read_text(encoding="utf-8", errors="replace")
                declared.update(_SETPROP_RE.findall(text))
                declared.update(_DECL_RE.findall(text))  # cssText / template-literal CSS
    # store WITH leading -- for easy membership
    return {"--" + n for n in declared}


def scan():
    declared = collect_declared()
    findings = []
    for path in _iter_css_files():
        raw = path.read_text(encoding="utf-8", errors="replace")
        original_lines = raw.splitlines()
        text = _strip_comments_keep_lines(raw)
        for m in _PROP_RE.finditer(text):
            prop = m.group("prop").lower()
            value = m.group("value")
            fv = _first_var(value)
            if not fv:
                continue
            name, fb = fv
            if name in declared:
                continue  # token IS declared; a defined-token collapse is a different class
            # classify the collapse shape
            shape = None
            if fb is None:
                shape = "bare-undeclared"  # (a) invalid value -> property dropped
            elif fb.lstrip().startswith("var("):
                fbv = _first_var(fb)
                if fbv:
                    fb_tier = _tier(fbv[0])
                    if prop in _TEXT_PROPS and fb_tier == "surface":
                        shape = "text-fallback-surface"  # (b) text = background
                    elif prop in _BG_PROPS and fb_tier == "text":
                        shape = "bg-fallback-text"  # (c) background = text
            if not shape:
                continue
            line_no = _line_of(text, m.start())
            if _has_marker(original_lines, line_no):
                continue
            try:
                rel = path.relative_to(_ROOT).as_posix()
            except ValueError:
                rel = path.as_posix()  # out-of-tree (unit-test temp dir)
            findings.append(
                {
                    "file": rel,
                    "line": line_no,
                    "prop": prop,
                    "token": name,
                    "shape": shape,
                    "snippet": (prop + ": " + value.strip())[:160],
                }
            )
    findings.sort(key=lambda f: (f["file"], f["line"]))
    return findings


def _load_baseline_count() -> int:
    if not _BASELINE.exists():
        return 0
    try:
        data = json.loads(_BASELINE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    return int(data.get("finding_count", 0))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    ap.add_argument("--strict", action="store_true", help="exit 1 if findings > baseline")
    ap.add_argument("--update-baseline", action="store_true", help="write current as baseline")
    args = ap.parse_args()

    findings = scan()

    if args.update_baseline:
        _BASELINE.parent.mkdir(parents=True, exist_ok=True)
        _BASELINE.write_text(
            json.dumps({"finding_count": len(findings), "findings": findings}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"baseline written: {len(findings)} findings")
        return 0

    if args.json:
        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"{f['file']}:{f['line']}  [{f['shape']}]  {f['token']}  |  {f['snippet']}")
        print(f"\nTOTAL undefined-token colour collapses: {len(findings)}")

    baseline = _load_baseline_count()
    if args.strict and len(findings) > baseline:
        print(f"FAIL: {len(findings)} findings > baseline {baseline}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
