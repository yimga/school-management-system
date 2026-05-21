"""Codemod: wrap theme-locked token references with a theme-aware first choice.

Companion to `scan_theme_locked_token_text.py`. The scanner flags declarations
like:

    color: var(--color-base-900);             /* fixed near-black */
    background: var(--color-base-100);        /* fixed light */
    border-color: var(--color-base-200);      /* fixed light */

These render the same color in every theme. On dark shells, dark text turns
invisible; on light surfaces re-themed dark, light backgrounds glare.

This codemod rewrites each flagged declaration to:

    color: var(--text-primary, var(--color-base-900));
    background: var(--surface-elevated, var(--color-base-100));
    border-color: var(--hairline, var(--color-base-200));

The fallback preserves the ORIGINAL value when `--text-primary` etc. are
undefined (e.g. on pages that don't load design-tokens.css). On every other
page the semantic token wins and the declaration flips correctly with theme.

Token-darkness → semantic mapping:

  TEXT (color: / fill: / stroke:)
    base-{700,800,900,950}        → --text-primary
    base-{500,600}                → --text-secondary
    base-{300,400}                → --text-tertiary
    bs-body-color                 → --text-primary
    bs-secondary-color            → --text-secondary
    bs-tertiary-color             → --text-tertiary
    bs-emphasis-color             → --text-primary
    color-primary-N00             → SKIP (brand color, intentional)
    color-{neutral,stone,slate}-N → mapped same as base-N

  SURFACE (background: / background-color:)
    base-{0,50,100,150,200}       → --surface-elevated
    base-{300,400}                → --surface-canvas
    base-{700,800,900,950}        → --surface-canvas (already dark — no change needed but wrap for symmetry)
    bs-body-bg                    → --surface-canvas

  HAIRLINE (border*-color: / outline-color:)
    base-{100,200,300,400}        → --hairline
    bs-border-color               → --hairline

Sites NOT in a theme-block AND not already wrapped with a semantic token are
candidates. Sites that ALREADY begin with `var(--text-*` / `--surface-*` /
`--hairline` / `--cp-text` / `--rmc-wcx-ink` are skipped (already adaptive).
Sites carrying `/* theme-locked-allow: <reason> */` on the same line are
skipped.

Usage:
    python scripts/codemod_theme_locked_tokens.py [--dry-run] [--path FILE]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = [
    ROOT / "static" / "css",
    ROOT / "static" / "marketing" / "css",
]
SKIP_FILES = {"design-tokens.css", "dark-mode-safety-net.css"}

_THEME_BLOCK = re.compile(
    r"(:root\b|\[data-(?:bs-|resolved-)?theme[^\]]*\]|\[data-rmc-[^\]]*\]|@media\s*\(\s*prefers-color-scheme"
    r"|\.(?:light|dark)-mode\b|body\.(?:light|dark)-mode\b|\.portal-backend-[a-z]+\b|html\.(?:light|dark)\b)",
    re.IGNORECASE,
)
_ALLOW_MARKER = re.compile(r"/\*\s*theme-locked-allow:[^*]+\*/")

# Recognize the FIRST var() in the value — if it's already semantic-theme-aware,
# leave it alone.
_THEME_AWARE_FIRST = re.compile(
    r"^\s*var\(\s*--(?:"
    r"text-primary|text-secondary|text-tertiary|text-muted|text-on-(?:brand|dark|light)"
    r"|surface-(?:bg|canvas|elevated|popover|overlay)"
    r"|hairline|elev-\d|material-blur"
    r"|cp-text|cp-muted|cp-panel-bg|cp-bg|cp-panel-border|cp-accent|cp-success|cp-warning|cp-danger"
    r"|rmc-wcx-(?:ink|muted|border|surface|accent|success|warning|danger)"
    r"|link-color|brand-(?:ink|fg|bg|primary|accent)"
    r"|bs-(?:body-color|primary|secondary|success|info|warning|danger|light|dark|body-bg|border-color|emphasis-color|secondary-bg|tertiary-bg|emphasis-bg)"  # Bootstrap auto-flips on [data-bs-theme="dark"]
    r"|admin-(?:surface|text|muted|subtle|content-[a-z]+|sidebar-[a-z]+|hero|nav|border)"
    r"|dashboard-(?:surface|text-strong|text-muted|theme-primary|theme-accent|bg|border|card-bg|card-border|glow-[a-z]|content-[a-z]+)"
    r"|portal-(?:bg|fg|surface|text|accent|border|nav)"
    r"|teacher-(?:bg|fg|surface|text)"
    r"|parent-(?:bg|fg|surface|text)"
    r"|student-(?:bg|fg|surface|text)"
    r"|school-(?:primary|accent|secondary)"
    r"|backend-(?:bg|fg|surface|text|sidebar)"
    r"|luxury-(?:surface|ink|hairline)"
    r")\b"
)

# Match a value that BEGINS with var(--<locked-token>...). We rewrap with
# semantic-first so the locked-token becomes the fallback.
_LOCKED_TEXT_TOKEN = re.compile(
    r"^(\s*)var\(\s*--(color-(?:base|neutral|stone|slate)-(\d{1,3})|bs-(?:secondary|tertiary|emphasis)-color)\b"
)
_LOCKED_SURFACE_TOKEN = re.compile(
    r"^(\s*)var\(\s*--(color-(?:base|neutral|stone|slate)-(\d{1,3})|bs-body-bg)\b"
)
_LOCKED_HAIRLINE_TOKEN = re.compile(
    r"^(\s*)var\(\s*--(color-(?:base|neutral|stone|slate)-(\d{1,3})|bs-border-color)\b"
)

# CSS declaration: prop : value ;
_DECL = re.compile(
    r"(?P<prop>color|background(?:-color)?|border(?:-color|-top-color|-bottom-color|-left-color|-right-color|-top|-bottom|-left|-right)?|outline(?:-color)?|fill|stroke)\s*:\s*(?P<val>[^;{}]+?)(?P<end>\s*;|\s*})",
    re.IGNORECASE,
)

# Border / outline shorthand value: matches `<width> <style> var(--<locked>...)`.
# The first var() in the value sits at the color slot — wrap it with --hairline.
_BORDER_SHORTHAND_VAR = re.compile(
    r"^(?P<prefix>\s*\d+(?:\.\d+)?(?:px|em|rem|\%)?\s+(?:solid|dashed|dotted|double|groove|ridge|inset|outset)\s+)(?P<var>var\([^)]*(?:\([^)]*\)[^)]*)*\))(?P<suffix>.*)$",
    re.IGNORECASE,
)


def _text_semantic_for(darkness: int) -> str:
    """Map a base-NNN token's numeric darkness to a text-* semantic token."""
    if darkness >= 700:
        return "--text-primary"
    if darkness >= 500:
        return "--text-secondary"
    if darkness <= 50:
        # Pure white / near-white — used as text-on-dark contexts.
        # --text-on-brand is the project's "always-white text" semantic.
        return "--text-on-brand"
    return "--text-tertiary"


def _surface_semantic_for(darkness: int) -> str:
    """Map a base-NNN token to a surface-* semantic token. Light tokens (0-200)
    are 'elevated' (cards/inputs); mid (300-400) are 'canvas' (page bg)."""
    if darkness <= 200:
        return "--surface-elevated"
    return "--surface-canvas"


def _semantic_first_choice(prop: str, value: str) -> str | None:
    """Return rewritten value (semantic-first + locked-fallback) or None if no rewrite."""
    prop_l = prop.lower()

    # Already adaptive — skip.
    if _THEME_AWARE_FIRST.match(value):
        return None

    if prop_l in {"color", "fill", "stroke"}:
        m = _LOCKED_TEXT_TOKEN.match(value)
        if not m:
            return None
        token_name = m.group(2)
        # bs-* are already partially theme-aware via Bootstrap, but mapping
        # them to a project semantic gives consistent dark-mode behavior.
        if token_name.startswith("bs-"):
            sem = {
                "bs-secondary-color": "--text-secondary",
                "bs-tertiary-color": "--text-tertiary",
                "bs-emphasis-color": "--text-primary",
            }[token_name]
        else:
            try:
                darkness = int(m.group(3))
            except (TypeError, ValueError):
                return None
            sem = _text_semantic_for(darkness)
        # Wrap: original `var(--color-base-900)` becomes `var(--text-primary, var(--color-base-900))`
        prefix = m.group(1)
        value[m.end():]
        # value started with "  var(--color-base-900<rest_until_;>"; we need to
        # find the matching close paren of the outer var() and wrap everything.
        return _wrap_with(value, prefix, sem)

    if prop_l in {"background", "background-color"}:
        m = _LOCKED_SURFACE_TOKEN.match(value)
        if not m:
            return None
        token_name = m.group(2)
        if token_name == "bs-body-bg":
            sem = "--surface-canvas"
        else:
            try:
                darkness = int(m.group(3))
            except (TypeError, ValueError):
                return None
            sem = _surface_semantic_for(darkness)
        prefix = m.group(1)
        return _wrap_with(value, prefix, sem)

    if prop_l in {"border-color", "border-top-color", "border-bottom-color",
                  "border-left-color", "border-right-color", "outline-color"}:
        m = _LOCKED_HAIRLINE_TOKEN.match(value)
        if not m:
            return None
        prefix = m.group(1)
        return _wrap_with(value, prefix, "--hairline")

    if prop_l in {"border", "border-top", "border-bottom", "border-left",
                  "border-right", "outline"}:
        # Shorthand: `<width> <style> var(--locked)`. Wrap the inner var()
        # only — leave width/style untouched.
        bm = _BORDER_SHORTHAND_VAR.match(value)
        if not bm:
            return None
        var_part = bm.group("var")
        # The var part must itself be a locked token to be a candidate.
        if not _LOCKED_HAIRLINE_TOKEN.match(var_part):
            return None
        # Wrap the var.
        wrapped_var = f"var(--hairline, {var_part})"
        return f"{bm.group('prefix')}{wrapped_var}{bm.group('suffix')}"

    return None


def _wrap_with(value: str, prefix: str, semantic: str) -> str:
    """Wrap the value with var(<semantic>, <original>). value starts with
    `<prefix>var(--<locked>...` — we keep the prefix outside the wrap so
    indentation is preserved."""
    inner = value[len(prefix):]
    # Strip any trailing whitespace from the original so the wrap is tight.
    inner_trimmed = inner.rstrip()
    trailing_ws = inner[len(inner_trimmed):]
    return f"{prefix}var({semantic}, {inner_trimmed}){trailing_ws}"


def _strip_comments_preserve_allow(text: str) -> str:
    def _sub(m: re.Match) -> str:
        body = m.group(0)
        if _ALLOW_MARKER.search(body):
            return body
        return ""
    return re.sub(r"/\*.*?\*/", _sub, text, flags=re.DOTALL)


def rewrite_file(path: Path) -> tuple[int, str]:
    """Walk one file and rewrite eligible declarations. Returns (changed_count, new_text).

    Theme-block awareness uses the same brace-walker as the scanner: a
    declaration inside `:root` / `[data-theme=*]` etc. is preserved (not
    rewritten) because the surrounding selector already gates the value.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    # We walk the file to find theme-block boundaries; for non-theme regions,
    # we apply substitutions inside each block-body slice.
    text = raw
    out: list[str] = []
    pos = 0
    changed = 0
    stack_is_theme: list[bool] = [False]
    # We need to walk and emit the file as we go so original comments + spacing
    # outside declarations are preserved.

    # Approach: split into segments around `{` and `}`. For each segment, if
    # current stack-top is "in a theme block", append unchanged. Otherwise,
    # run _DECL substitution.
    while pos < len(text):
        next_open = text.find("{", pos)
        next_close = text.find("}", pos)
        if next_open == -1 and next_close == -1:
            out.append(text[pos:])
            break
        if next_open != -1 and (next_close == -1 or next_open < next_close):
            # Selector text from `pos` to next_open (inclusive of '{').
            selector_text = text[pos:next_open + 1]
            out.append(selector_text)
            # Push new stack entry: in-theme if selector includes a theme block
            # OR if any ancestor was in-theme.
            in_theme = bool(_THEME_BLOCK.search(text[pos:next_open])) or stack_is_theme[-1]
            stack_is_theme.append(in_theme)
            pos = next_open + 1
        else:
            # Body segment from `pos` to next_close (exclusive).
            body = text[pos:next_close]
            currently_in_theme = stack_is_theme[-1] if stack_is_theme else False
            if currently_in_theme:
                out.append(body)
            else:
                # Walk declarations in this body. Skip lines carrying allow marker.
                def _maybe_rewrite(m: re.Match) -> str:
                    prop = m.group("prop")
                    val = m.group("val")
                    end = m.group("end")
                    full_match = m.group(0)
                    # Honor same-line allow marker
                    line_start = body.rfind("\n", 0, m.start()) + 1
                    line_end = body.find("\n", m.end())
                    if line_end == -1:
                        line_end = len(body)
                    same_line = body[line_start:line_end]
                    if _ALLOW_MARKER.search(same_line):
                        return full_match
                    # Separate trailing `!important` so it stays OUTSIDE the
                    # wrap. Otherwise wrapping produces invalid CSS like
                    # `var(--text-primary, var(--color-base-900) !important)`.
                    val_stripped = val
                    important_suffix = ""
                    important_match = re.search(r"\s+!important\s*$", val_stripped)
                    if important_match:
                        important_suffix = " !important"
                        val_stripped = val_stripped[:important_match.start()]
                    new_val = _semantic_first_choice(prop, val_stripped)
                    if new_val is None:
                        return full_match
                    nonlocal changed
                    changed += 1
                    return f"{prop}: {new_val}{important_suffix}{end}"
                body_new = _DECL.sub(_maybe_rewrite, body)
                out.append(body_new)
            # Emit the closing brace.
            out.append("}")
            if stack_is_theme:
                stack_is_theme.pop()
            pos = next_close + 1
    return changed, "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Show summary; don't write files.")
    parser.add_argument("--path", type=Path, default=None,
                        help="Rewrite only this file (relative to repo root or absolute).")
    args = parser.parse_args()

    files: list[Path]
    if args.path:
        f = args.path
        if not f.is_absolute():
            f = ROOT / args.path
        files = [f]
    else:
        files = []
        for d in SEARCH_DIRS:
            if not d.exists():
                continue
            for f in d.rglob("*.css"):
                if f.name in SKIP_FILES:
                    continue
                files.append(f)

    total_changed = 0
    files_changed = 0
    for f in files:
        n, new_text = rewrite_file(f)
        if n == 0:
            continue
        total_changed += n
        files_changed += 1
        rel = f.relative_to(ROOT) if ROOT in f.parents or f.is_relative_to(ROOT) else f
        print(f"  {n:4}  {str(rel).replace(chr(92), '/')}")
        if not args.dry_run:
            f.write_text(new_text, encoding="utf-8")

    print(f"\n{total_changed} declaration(s) rewritten across {files_changed} file(s)"
          + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
