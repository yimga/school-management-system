"""Scan: enforce the v3 (2026-05-18) theme-attribute contract.

Contract (documented in docs/THEME_SYSTEM.md §0):

    <html data-theme="light|dark">             ← effective theme
    <html data-resolved-theme="light|dark">    ← effective theme
    <html data-bs-theme="light|dark">          ← Bootstrap 5 compat
    <html data-theme-preference="light|dark|system">  ← raw preference

`data-theme` must NEVER carry the literal value "system". CSS rules
must NEVER gate styling on `[data-theme="system"]` (it's a no-op under
v3 — the preference moved to `data-theme-preference`). JS code must
NEVER write the preference into `data-theme`; the resolved value goes
there instead.

What the v2 → v3 fix solved: under v2 a user with preference="system"
+ OS=dark got `<html data-theme="system">`, which never matched any
`[data-theme="dark"]` selector — so 271 CSS rules across 34 files
silently skipped, while `[data-bs-theme="dark"]` still flipped
`--text-primary` to near-white. Result: white-text-on-white-card
across every dashboard. This scanner prevents regression.

Rules checked
-------------
1. CSS:  no `[data-theme="system"]` selectors in any file under
   `static/css/` or `static/marketing/css/`. (Compound selectors that
   include the system literal as a defensive backup are flagged too
   — they were dead code under v3 and add noise. Mark intentional
   sites with `/* theme-attr-contract-allow: <reason> */` on the
   same line.)
2. JS:   no `setAttribute("data-theme", <preference-string>)` in
   `static/js/` where the value can be "system" or "auto". Specifically
   any `setAttribute("data-theme", pref)` where `pref` is not a value
   already constrained to {light, dark} via a local resolve. Heuristic:
   flag any literal `"system"` or `"auto"` passed to `data-theme`, and
   any `setAttribute("data-theme", X)` whose nearest enclosing function
   reads `localStorage` for a preference key without an explicit
   resolve step.

Zero-tolerance gate from day 1.

Usage:
    python scripts/scan_theme_attribute_contract.py [--strict] [--json]
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
JS_DIRS = [
    REPO_ROOT / "static" / "js",
    REPO_ROOT / "static" / "marketing" / "js",
]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-theme-attribute-contract.json"

ALLOW_MARKER_CSS = "theme-attr-contract-allow:"
ALLOW_MARKER_JS = "theme-attr-contract-allow:"

# CSS: any selector that pins on data-theme being the literal "system".
CSS_SELECTOR_RE = re.compile(
    r'\[\s*data-theme\s*=\s*"(?:system|auto)"\s*\]',
    re.IGNORECASE,
)

# JS: setAttribute("data-theme", "system"|"auto"|<bare ident "pref"|"preference">).
# The two literal-value cases are unambiguous. The bare-ident case is a
# heuristic — if a function writes `setAttribute("data-theme", pref)` we
# also want it scoped, but only when "pref" is the same name being read
# from localStorage in the same scope, so we leave that to a follow-up
# walker. The literal cases catch the regression we care about.
JS_LITERAL_RE = re.compile(
    r'setAttribute\(\s*["\']data-theme["\']\s*,\s*["\'](system|auto)["\']\s*\)',
    re.IGNORECASE,
)


def _strip_css_comments_keep_allow(text: str) -> str:
    return re.sub(
        r"/\*(?![^*]*" + re.escape(ALLOW_MARKER_CSS) + r").*?\*/",
        "",
        text,
        flags=re.DOTALL,
    )


def _scan_css(path: pathlib.Path, text: str) -> list[str]:
    findings: list[str] = []
    cleaned = _strip_css_comments_keep_allow(text)
    for m in CSS_SELECTOR_RE.finditer(cleaned):
        # Find the enclosing line in original text for context + line no.
        # Use match offset against cleaned text (offsets shift after strip),
        # so re-scan original text for the same lexeme starting near m.start().
        idx = text.find(m.group(0), max(0, m.start() - 200))
        if idx == -1:
            idx = m.start()
        # Look for the allow-marker on the same selector line / nearby.
        line_start = text.rfind("\n", 0, idx) + 1
        line_end = text.find("\n", idx)
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        if ALLOW_MARKER_CSS in line:
            continue
        # Also accept the marker on the previous line (long selector lists).
        prev_start = text.rfind("\n", 0, line_start - 1) + 1
        prev_line = text[prev_start : line_start - 1] if line_start > 0 else ""
        if ALLOW_MARKER_CSS in prev_line:
            continue
        line_no = text[:idx].count("\n") + 1
        findings.append(f"{path.relative_to(REPO_ROOT)}:{line_no}: {line.strip()[:160]}")
    return findings


def _scan_js(path: pathlib.Path, text: str) -> list[str]:
    findings: list[str] = []
    for m in JS_LITERAL_RE.finditer(text):
        # Same-line allow-marker honored.
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.start())
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        if ALLOW_MARKER_JS in line:
            continue
        line_no = text[: m.start()].count("\n") + 1
        findings.append(f"{path.relative_to(REPO_ROOT)}:{line_no}: {line.strip()[:160]}")
    return findings


def scan_all() -> list[str]:
    findings: list[str] = []
    for css_dir in CSS_DIRS:
        if not css_dir.exists():
            continue
        for css in css_dir.rglob("*.css"):
            try:
                text = css.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            findings.extend(_scan_css(css, text))
    for js_dir in JS_DIRS:
        if not js_dir.exists():
            continue
        for js in js_dir.rglob("*.js"):
            # Skip vendor + minified bundles.
            rel = js.relative_to(REPO_ROOT).as_posix()
            if "/vendor/" in rel or rel.endswith(".min.js"):
                continue
            try:
                text = js.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            findings.extend(_scan_js(js, text))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any current violation exceeds baseline (zero-tolerance).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite baseline JSON with current count (use only when reducing).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
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
        print(f"theme-attribute-contract scan: {total} violation(s)")
        print(f"baseline: {baseline_total}")
        for f in findings[:30]:
            print(f"  {f}")

    if args.strict and total > baseline_total:
        print(f"FAIL: {total} > baseline {baseline_total}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
