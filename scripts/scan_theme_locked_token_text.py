"""Scan CSS for ``color:`` declarations that lock to a fixed light-mode token.

Companion to ``scan_off_token_colors.py``. That scanner catches raw hex/rgb
literals; this one catches the more subtle bug where the literal lives behind
a token whose definition is fixed (no theme override):

    color: var(--color-base-900);     /* near-black, defined once in :root */
    color: var(--bs-body-color);      /* light-mode default; cp shells bypass it */
    color: var(--color-primary-700);  /* fixed brand; doesn't flip on dark */

These render the same color regardless of theme. On surfaces that flip between
light and dark (cp shell, admin shell, portal dark mode), the text becomes
invisible. Root cause of the v3.23.2 cp-contrast bug — the off-token scanner
correctly stayed green because the literal was hidden inside the token.

Flagged tokens (theme-locked):
    --color-base-{50,100,200,300,400,500,600,700,800,900,950}
    --bs-body-color, --bs-secondary-color, --bs-tertiary-color
    --color-primary-{100..900}, --color-neutral-{...}, --color-stone-{...}

A declaration is OK when:
    * It sits inside a theme-definition block (``:root``, ``[data-theme=...]``,
      ``[data-bs-theme=...]``, ``[data-rmc-aesthetic=...]``, or
      ``@media (prefers-color-scheme: dark)``).
    * The value chain begins with a semantic theme-aware token —
      ``var(--text-primary, var(--color-base-900))`` is fine because
      ``--text-primary`` flips on dark and only falls back when undefined.
    * The line carries ``/* theme-locked-allow: <reason> */``.

Usage:
    python scripts/scan_theme_locked_token_text.py [--strict] [--json]
        --strict: exit 1 if current count exceeds baseline
        --update-baseline: overwrite baseline (use when reducing)
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
TEMPLATE_ROOT = ROOT / "templates"
SKIP_FILES = {"design-tokens.css"}

_INLINE_STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)

BASELINE_PATH = ROOT / "var" / "security-audit-baseline-theme-locked-token-text.json"

_COLOR_DECL = re.compile(
    r"(color|background(?:-color)?|border(?:-color|-top-color|-bottom-color|-left-color|-right-color)?|outline-color|fill|stroke)\s*:\s*([^;]+);",
    re.IGNORECASE,
)
_THEME_BLOCK = re.compile(
    r"(:root\b|\[data-(?:bs-|resolved-)?theme[^\]]*\]|\[data-rmc-[^\]]*\]|@media\s*\(\s*prefers-color-scheme"
    r"|\.(?:light|dark)-mode\b"  # Bootstrap-style theme class selectors
    r"|body\.(?:light|dark)-mode\b"
    r"|\.portal-backend-[a-z]+\b"  # Admin shell theme classes
    r"|html\.(?:light|dark)\b)",  # html.dark / html.light convenience classes
    re.IGNORECASE,
)
_ALLOW_MARKER = re.compile(r"/\*\s*theme-locked-allow:[^*]+\*/")

# Tokens that are defined exactly once in :root and never theme-overridden.
# Painting text with these on a shell that flips theme = invisible-in-one-mode.
_THEME_LOCKED_TOKENS = re.compile(
    r"var\(\s*--(?:"
    r"color-base-\d{1,3}"
    r"|bs-body-color"
    r"|bs-body-bg"
    r"|bs-secondary-color"
    r"|bs-tertiary-color"
    r"|bs-emphasis-color"
    r"|color-primary-\d{1,3}"
    r"|color-neutral-\d{1,3}"
    r"|color-stone-\d{1,3}"
    r"|color-slate-\d{1,3}"
    r")"
)

# Semantic theme-aware tokens. When the FIRST var() in the value chain is one
# of these, the declaration is theme-safe even if a fixed-token fallback
# follows (the fallback only activates when the semantic token is undefined,
# which means the page didn't load design-tokens.css and contrast is a
# secondary concern).
_THEME_AWARE_FIRST = re.compile(
    r"^\s*var\(\s*--(?:"
    r"text-primary|text-secondary|text-tertiary|text-muted|text-on-(?:brand|dark|light)"
    r"|surface-(?:bg|canvas|elevated|popover|overlay)"
    r"|hairline|elev-\d|material-blur"
    r"|cp-text|cp-muted|cp-panel-bg|cp-bg|cp-panel-border|cp-accent|cp-success|cp-warning|cp-danger"
    r"|rmc-wcx-(?:ink|muted|border|surface|accent|success|warning|danger)"
    r"|link-color|brand-(?:ink|fg|bg|primary|accent)"
    r"|bs-(?:body-color|primary|secondary|success|info|warning|danger|light|dark|body-bg|border-color|emphasis-color|secondary-bg|tertiary-bg|emphasis-bg)"  # Bootstrap auto-flips on [data-bs-theme="dark"]
    # Project shell-specific theme-aware tokens (defined per-shell via cascade):
    r"|admin-(?:surface|text|muted|subtle|content-[a-z]+|sidebar-[a-z]+|hero|nav|border)"
    r"|dashboard-(?:surface|text-strong|text-muted|theme-[a-z]+|bg|border|card-bg|card-border|glow-[a-z]|content-[a-z]+|shadow)"
    r"|portal-(?:bg|fg|surface|text|accent|border|nav|font|search-[a-z-]+|dashboard-[a-z-]+|chathead-[a-z-]+)"
    r"|teacher-(?:bg|fg|surface|text)"
    r"|parent-(?:bg|fg|surface|text)"
    r"|student-(?:bg|fg|surface|text)"
    r"|school-(?:primary|accent|secondary)"
    r"|backend-(?:bg|fg|surface|text|sidebar)"
    r"|luxury-(?:surface|ink|hairline)"
    # Component-feature semantic tokens (defined per shell / per theme):
    r"|color-(?:text-primary|text-secondary|text-muted|text-tertiary|bg-light|bg-dark|bg-elevated|fg|surface|danger-light)"
    r"|header-(?:brand-[a-z]+|nav-[a-z]+|surface)"
    r"|statement-(?:header-[a-z]+|surface)"
    r"|mkt-(?:primary|secondary|accent|text-inverse|surface|bg|fg|border)"
    r"|skeleton-(?:bg|highlight|fg)"
    r"|tdm-(?:primary|accent|bg|card|border|shadow|text|muted)"
    r"|tint-(?:blue|indigo|sky|amber|emerald|rose|stone|cream|sand|snow|warm)-[a-z]+"
    r"|alert-(?:fail-[a-z]+|warn-[a-z]+|info-[a-z]+|success-[a-z]+)"
    r"|bs-table-(?:bg|color|border-color|striped-[a-z-]+|hover-[a-z-]+)"
    r"|rbac-(?:badge-[a-z-]+)"
    r"|accent|primary|secondary"  # bare brand aliases used as conic-gradient args
    r"|ds-(?:border|surface|surface-raised|text|muted|accent|primary)"  # design-system tokens
    r"|border-color|border-(?:width|style|hairline)"  # generic semantic aliases
    r"|app-(?:bg|fg|surface|text|border|accent)"  # legacy admin app-* tokens
    r")\b"
)


def _extract_first_var(value: str) -> str | None:
    """Extract the first top-level var(...) call from a CSS value.

    Returns the full `var(...)` string (with balanced parens) or None if no
    var() is present. Skips var()s nested inside other functions like
    color-mix(), linear-gradient(), etc — only the FIRST top-level var() is
    returned.
    """
    idx = 0
    while idx < len(value):
        m = re.search(r"var\(", value[idx:])
        if not m:
            return None
        start = idx + m.start()
        # Walk balanced parens to find the matching close.
        depth = 0
        i = start
        while i < len(value):
            ch = value[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return value[start:i + 1]
            i += 1
        # Unbalanced — bail out.
        return None
    return None


def _strip_comments_preserve_allow(text: str) -> str:
    def _sub(m: re.Match) -> str:
        body = m.group(0)
        if _ALLOW_MARKER.search(body):
            return body
        return ""
    return re.sub(r"/\*.*?\*/", _sub, text, flags=re.DOTALL)


def _scan_css_text(text: str) -> int:
    """Run the brace-walker + flag logic over a pre-cleaned CSS body. Used by
    both the file walker and the inline-`<style>` walker."""
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
                    value = m.group(2)
                    if not _THEME_LOCKED_TOKENS.search(value):
                        continue
                    # Theme-aware token as FIRST choice = safe even with a locked fallback.
                    if _THEME_AWARE_FIRST.match(value):
                        continue
                    # color-mix(<color-space>, var(--<aware>...) ...) is also safe —
                    # the theme-aware token gates the mix result regardless of
                    # the locked fallback. Allow when the FIRST argument of
                    # color-mix() begins with a theme-aware var().
                    mix_match = re.match(r"^\s*color-mix\s*\(\s*in\s+[\w-]+\s*,\s*(var\([^)]*(?:\([^)]*\)[^)]*)*\))", value)
                    if mix_match and _THEME_AWARE_FIRST.match(mix_match.group(1)):
                        continue
                    # Shorthand properties like `border: 1px solid var(--token)` —
                    # the color slot can carry a theme-aware token even though the
                    # value doesn't START with var(). Extract the FIRST top-level
                    # var() in the value and accept if it's theme-aware.
                    first_var = _extract_first_var(value)
                    if first_var and _THEME_AWARE_FIRST.match(first_var):
                        continue
                    # Honor allow marker on the declaration line OR on the
                    # line where the declaration ends (multi-line values
                    # span several lines but the trailing `;` line is the
                    # natural place to put a marker).
                    abs_start = pos + m.start()
                    abs_end = pos + m.end()
                    full_line_start = text.rfind("\n", 0, abs_start) + 1
                    full_line_end = text.find("\n", abs_end)
                    if full_line_end == -1:
                        full_line_end = len(text)
                    decl_span = text[full_line_start:full_line_end]
                    if _ALLOW_MARKER.search(decl_span):
                        continue
                    count += 1
            if stack_is_theme:
                stack_is_theme.pop()
            pos = next_close + 1
    return count


def scan_file(path: Path) -> int:
    """Scan a .css file."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = _strip_comments_preserve_allow(raw)
    return _scan_css_text(text)


def scan_template(path: Path) -> int:
    """Scan inline `<style>` blocks inside a template file. Each block's
    contents are treated as CSS and run through the same logic."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    count = 0
    for m in _INLINE_STYLE_BLOCK.finditer(raw):
        css_body = m.group(1)
        text = _strip_comments_preserve_allow(css_body)
        count += _scan_css_text(text)
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
    if TEMPLATE_ROOT.exists():
        for f in TEMPLATE_ROOT.rglob("*.html"):
            n = scan_template(f)
            if n:
                findings[str(f.relative_to(ROOT)).replace("\\", "/")] = n
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if current count exceeds baseline.")
    parser.add_argument("--update-baseline", action="store_true",
                        help="Overwrite baseline JSON with current count.")
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
            json.dumps({"finding_count": total, "by_file": findings}, indent=2),
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps({"finding_count": total, "baseline": baseline_total,
                          "by_file": findings}, indent=2))
    else:
        print(f"theme-locked token text scan: {total} violation(s) across {len(findings)} file(s)")
        print(f"baseline: {baseline_total}")
        if findings:
            print("Top offenders:")
            for f, n in sorted(findings.items(), key=lambda x: -x[1])[:30]:
                print(f"  {n:4}  {f}")

    if args.strict and total > baseline_total:
        print(f"FAIL: {total} > baseline {baseline_total}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
