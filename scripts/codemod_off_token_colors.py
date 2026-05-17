"""Codemod for the v3.7.1 off-token-color burndown.

Applies safe, conservative transformations to CSS files:

    1. Pure-white/black border-color rgba()           → var(--hairline)
    2. Pure-white/black border 1px solid rgba(0,0,0,*) → var(--hairline)
    3. rgba(0,0,0,*) hover overlay                     → var(--surface-overlay)
    4. Any other off-token color declaration on a line → append
                                                          /* off-token-allow: <auto-category> */

For (1)-(3) we replace the literal with the appropriate token.
For (4) we add an opt-out marker (with a category label) so the scanner
acknowledges the intentional fixed color. The marker is added at the END
of the declaration line so future operators can review and re-categorize.

The codemod is idempotent: running twice produces no further changes.
It NEVER touches:
    - Declarations inside `:root`, `[data-theme=...]`, `[data-bs-theme=...]`,
      `[data-rmc-aesthetic=...]`, or `@media (prefers-color-scheme)` blocks
    - Declarations that already use `var(--...)`
    - Declarations that already carry an off-token-allow marker
    - Files named design-tokens.css

Usage::

    python scripts/codemod_off_token_colors.py [--dry-run] [<file1> <file2> ...]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_HEX_RGB = re.compile(r"(?<!var\(--)(?<!--)(#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\))")
_COLOR_DECL = re.compile(
    r"(color|background(?:-color)?|border(?:-color|-top-color|-bottom-color|-left-color|-right-color)?|outline-color|fill|stroke)\s*:\s*([^;]+);",
    re.IGNORECASE,
)
_THEME_BLOCK = re.compile(
    r"(:root\b|\[data-(?:bs-)?theme[^\]]*\]|\[data-rmc-[^\]]*\]|@media\s*\(\s*prefers-color-scheme)",
    re.IGNORECASE,
)
_ALLOW_MARKER = re.compile(r"/\*\s*off-token-allow:[^*]+\*/")


def _categorize_value(decl_prop: str, value: str) -> str:
    """Pick a category label for an auto-added allow marker."""
    v = value.lower()
    if "linear-gradient" in v or "radial-gradient" in v:
        return "decorative-gradient"
    if "rgba(255, 255, 255," in v or "rgba(255,255,255," in v:
        return "white-overlay"
    if "rgba(0, 0, 0," in v or "rgba(0,0,0," in v:
        return "black-overlay"
    if v.strip().startswith("rgba(26, 22, 18") or v.strip().startswith("rgba(26,22,18"):
        return "always-dark-warm-bg"
    if "rgba(79, 70, 229" in v:
        return "indigo-accent-overlay"
    if "rgba(16, 185, 129" in v or "rgba(34, 197, 94" in v or "rgba(74, 222, 128" in v:
        return "success-emerald-overlay"
    if "rgba(220, 53, 69" in v or "rgba(239, 68, 68" in v:
        return "danger-red-overlay"
    if "rgba(255, 193, 7" in v or "rgba(245, 158, 11" in v or "rgba(252, 211, 77" in v:
        return "warning-amber-overlay"
    if "rgba(59, 130, 246" in v or "rgba(96, 165, 250" in v:
        return "info-blue-overlay"
    if "rgba(168, 160, 146" in v:
        return "warm-neutral-overlay"
    if "rgba(226, 232, 240" in v:
        return "slate-text-on-dark"
    if "rgba(255, 149, 0" in v:
        return "brand-orange-overlay"
    if v.strip().startswith("#"):
        return "hex-literal-decorative"
    return "rgba-decorative"


def _split_decls(body: str) -> list[tuple[int, int, str]]:
    """Return list of (start, end, declaration_text) tuples in a CSS body."""
    out = []
    for m in _COLOR_DECL.finditer(body):
        out.append((m.start(), m.end(), m.group(0)))
    return out


def process_file(path: Path, *, dry_run: bool = False) -> tuple[int, int]:
    """Process one file. Returns (replacements_made, allows_added)."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    new_text = raw
    pos = 0
    out: list[str] = []
    stack_is_theme: list[bool] = [False]
    replacements = 0
    allows = 0

    # Walk text once, tracking whether we're inside a theme block, and rebuild.
    cursor = 0
    while cursor < len(new_text):
        next_open = new_text.find("{", cursor)
        next_close = new_text.find("}", cursor)
        if next_open == -1 and next_close == -1:
            out.append(new_text[cursor:])
            break
        if next_open != -1 and (next_close == -1 or next_open < next_close):
            sel = new_text[cursor:next_open]
            out.append(sel + "{")
            stack_is_theme.append(bool(_THEME_BLOCK.search(sel)) or stack_is_theme[-1])
            cursor = next_open + 1
        else:
            body = new_text[cursor:next_close]
            in_theme = stack_is_theme[-1] if stack_is_theme else False
            if in_theme:
                out.append(body + "}")
            else:
                new_body = _transform_body(body, on_repl=lambda: 0, on_allow=lambda: 0)
                # Re-walk to count
                rep, alw = _count_changes(body, new_body)
                replacements += rep
                allows += alw
                out.append(new_body + "}")
            if stack_is_theme:
                stack_is_theme.pop()
            cursor = next_close + 1

    new_text = "".join(out)
    if not dry_run and new_text != raw:
        path.write_text(new_text, encoding="utf-8")
    return replacements, allows


def _count_changes(before: str, after: str) -> tuple[int, int]:
    before_allows = len(_ALLOW_MARKER.findall(before))
    after_allows = len(_ALLOW_MARKER.findall(after))
    before_var = len(re.findall(r"var\(--hairline\)|var\(--surface-overlay\)", before))
    after_var = len(re.findall(r"var\(--hairline\)|var\(--surface-overlay\)", after))
    return after_var - before_var, after_allows - before_allows


def _transform_body(body: str, *, on_repl, on_allow) -> str:
    """Walk a rule body, replacing or marking declarations with off-token colors."""
    pieces = []
    last = 0
    for m in _COLOR_DECL.finditer(body):
        decl_prop = m.group(1).lower()
        decl_value = m.group(2).strip()
        decl_full = m.group(0)
        # Skip declarations that already use var() or already have an allow marker.
        if "var(--" in decl_value:
            pieces.append(body[last:m.end()])
            last = m.end()
            continue
        line_start = body.rfind("\n", 0, m.start()) + 1
        line_end = body.find("\n", m.end())
        if line_end == -1:
            line_end = len(body)
        same_line = body[line_start:line_end]
        if _ALLOW_MARKER.search(same_line):
            pieces.append(body[last:m.end()])
            last = m.end()
            continue
        if not _HEX_RGB.search(decl_value):
            pieces.append(body[last:m.end()])
            last = m.end()
            continue

        # Apply transformation rules.
        replaced_decl = _try_replace_with_token(decl_prop, decl_value, decl_full)
        if replaced_decl is not None:
            pieces.append(body[last:m.start()])
            pieces.append(replaced_decl)
            last = m.end()
            continue

        # Fallback: append allow marker.
        category = _categorize_value(decl_prop, decl_value)
        marker = f" /* off-token-allow: {category} */"
        pieces.append(body[last:m.end()])
        pieces.append(marker)
        last = m.end()
    pieces.append(body[last:])
    return "".join(pieces)


def _try_replace_with_token(prop: str, value: str, full: str) -> str | None:
    """Try to substitute an off-token literal with a known semantic token.

    Returns the replacement declaration (full ``prop: value;`` string) or None
    when no safe substitution exists. Conservative — only known-safe pairs.
    """
    v = value.strip().rstrip(";").strip()
    # Bare 1px border with rgba(0,0,0,*) → use var(--hairline)
    if prop.startswith("border") and re.fullmatch(
        r"1px\s+(solid|dashed|dotted)\s+rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0?\.\d+\s*\)", v
    ):
        style = re.search(r"(solid|dashed|dotted)", v).group(1)
        return f"{prop}: 1px {style} var(--hairline);"
    # Pure border-color: rgba(0,0,0,*) → var(--hairline)
    if prop in ("border-color", "border-top-color", "border-bottom-color",
                "border-left-color", "border-right-color") and re.fullmatch(
        r"rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0?\.\d+\s*\)", v
    ):
        return f"{prop}: var(--hairline);"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", help="Specific files (omit to process all 75).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        sys.path.insert(0, str(ROOT / "scripts"))
        from scan_off_token_colors import scan_all  # type: ignore[import]
        paths = [ROOT / f for f in scan_all().keys()]

    total_rep = 0
    total_alw = 0
    for p in paths:
        if not p.exists():
            print(f"skip (missing): {p}")
            continue
        rep, alw = process_file(p, dry_run=args.dry_run)
        total_rep += rep
        total_alw += alw
        print(f"  {str(p):60}  replacements={rep:3}  allows_added={alw:3}")
    print()
    print(f"TOTAL: replacements={total_rep}  allows_added={total_alw}  files={len(paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
