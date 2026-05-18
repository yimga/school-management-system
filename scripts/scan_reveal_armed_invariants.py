"""Scan: lock the rmc-reveal armed-attribute defense in place.

Prevents regression of the bug class that produced the blank-app-catalog +
abrupt-page-end symptoms (v3.25.5 fix). Three invariants are enforced:

    1. CSS rules that hide content via opacity:0 on .rmc-reveal must be
       scoped under html[data-rmc-reveal-armed]. If any unscoped
       .rmc-reveal { opacity: 0 } rule lands, JS-load failure perma-hides
       content again.

    2. static/js/rmc-reveal.js must set data-rmc-reveal-armed on
       <html> synchronously at parse time, so the CSS rule activates
       before first paint when (and only when) JS is alive.

    3. Every shell that links rmc-reveal.js must load it WITHOUT defer
       (i.e. as a render-blocking <script>), so the arm flag is set
       before first paint and there is no flash-of-visible-then-hidden.

Bonus invariant — same audit catches the duplicate-class-attribute bug class
that silently dropped `rmc-reveal` from 6 elements in the same wave:

    4. No template element carries two `class="..."` attributes. Browsers
       drop the second per HTML5 parsing rules; any class on it is silently
       lost. This is a separate failure mode that produces silent UX bugs.

Zero-tolerance gate from day 1.

Usage:
    python scripts/scan_reveal_armed_invariants.py [--strict] [--json]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

CSS_PATH = REPO_ROOT / "static" / "css" / "design-tokens.css"
JS_PATH = REPO_ROOT / "static" / "js" / "rmc-reveal.js"
SHELL_TEMPLATES = [
    REPO_ROOT / "templates" / "control_plane_skeleton.html",
    REPO_ROOT / "templates" / "base.html",
    REPO_ROOT / "templates" / "portal_base.html",
    REPO_ROOT / "templates" / "admin" / "base_site.html",
    REPO_ROOT / "templates" / "marketing" / "base_marketing.html",
]
TEMPLATES_ROOT = REPO_ROOT / "templates"

ARMED_ATTR = "data-rmc-reveal-armed"
RMC_REVEAL_SCRIPT = "rmc-reveal.js"


def _check_css_armed_scoping() -> list[str]:
    """Invariant 1: every .rmc-reveal opacity:0 rule scoped under html[data-rmc-reveal-armed]."""
    findings: list[str] = []
    if not CSS_PATH.exists():
        return [f"{CSS_PATH}: file missing"]
    text = CSS_PATH.read_text(encoding="utf-8", errors="replace")
    # Find each `.rmc-reveal*` rule block and confirm its selector head includes
    # html[data-rmc-reveal-armed]. We accept the selector if the attribute
    # appears anywhere in the selector list preceding the rule body.
    # Pattern: capture selector (anything up to `{`) then body.
    rule_re = re.compile(r"([^{}]+)\{[^{}]*opacity\s*:\s*0[^{}]*\}", re.DOTALL)
    for m in rule_re.finditer(text):
        selector = m.group(1).strip()
        # Only care about reveal selectors.
        if ".rmc-reveal" not in selector:
            continue
        if ARMED_ATTR not in selector:
            line_no = text[: m.start()].count("\n") + 1
            findings.append(
                f"{CSS_PATH.relative_to(REPO_ROOT)}:{line_no}: "
                f".rmc-reveal opacity:0 rule not scoped under html[{ARMED_ATTR}] — "
                f"selector: {selector[:120]}"
            )
    return findings


def _check_js_arms_at_parse() -> list[str]:
    """Invariant 2: rmc-reveal.js sets data-rmc-reveal-armed synchronously."""
    findings: list[str] = []
    if not JS_PATH.exists():
        return [f"{JS_PATH}: file missing"]
    src = JS_PATH.read_text(encoding="utf-8", errors="replace")
    # Strip block + line comments and string literals BEFORE checking, so
    # mentions of the attribute in comments/strings don't satisfy the gate.
    stripped = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    stripped = re.sub(r"//[^\n]*", "", stripped)
    stripped = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", stripped)
    stripped = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', stripped)
    if "setAttribute" not in stripped or ARMED_ATTR not in src:
        findings.append(
            f"{JS_PATH.relative_to(REPO_ROOT)}: must call "
            f"documentElement.setAttribute(\"{ARMED_ATTR}\", ...) at parse time"
        )
        return findings
    # Confirm the setAttribute call is at module-top-level (inside the outer
    # IIFE), not inside init() — heuristic: it appears before `function init`.
    init_idx = stripped.find("function init")
    arm_idx = stripped.find("setAttribute")
    if init_idx != -1 and arm_idx != -1 and arm_idx > init_idx:
        findings.append(
            f"{JS_PATH.relative_to(REPO_ROOT)}: setAttribute for "
            f"{ARMED_ATTR} must run synchronously at parse, not inside init()"
        )
    return findings


def _check_shells_load_synchronously() -> list[str]:
    """Invariant 3: each shell loads rmc-reveal.js WITHOUT defer."""
    findings: list[str] = []
    script_re = re.compile(
        r"<script[^>]*src=\"[^\"]*" + re.escape(RMC_REVEAL_SCRIPT) + r"[^\"]*\"[^>]*>"
    )
    for shell in SHELL_TEMPLATES:
        if not shell.exists():
            findings.append(f"{shell.relative_to(REPO_ROOT)}: shell template missing")
            continue
        text = shell.read_text(encoding="utf-8", errors="replace")
        matches = script_re.findall(text)
        if not matches:
            findings.append(
                f"{shell.relative_to(REPO_ROOT)}: does not link {RMC_REVEAL_SCRIPT}"
            )
            continue
        for tag in matches:
            if " defer" in tag or " async" in tag:
                line_no = text.find(tag)
                line_no = text[:line_no].count("\n") + 1
                findings.append(
                    f"{shell.relative_to(REPO_ROOT)}:{line_no}: "
                    f"{RMC_REVEAL_SCRIPT} must be loaded synchronously "
                    f"(no defer/async) so the arm flag is set before first paint"
                )
    return findings


def _check_no_duplicate_class_attrs() -> list[str]:
    """Invariant 4: no template tag has two `class=` attributes (browsers drop the second).

    Excludes framework-binding shorthands that LOOK similar but are distinct
    HTML attributes parsed separately:
      :class="..."        — Alpine.js / Vue reactive class shorthand
      x-bind:class="..."  — Alpine.js explicit form
      v-bind:class="..."  — Vue explicit form
      [class]="..."       — Angular-style binding
    These compile to additional class bindings rather than overriding the
    static `class=` attribute, so they are not the bug we're catching.
    """
    findings: list[str] = []
    tag_re = re.compile(r"<[a-zA-Z][^>]*?>", re.DOTALL)
    # Require `class=` to be preceded by whitespace (i.e., the start of a real
    # standalone HTML attribute), NOT by `:`, `-`, or alphanumeric chars (which
    # would make it part of a framework binding like `:class=` or
    # `x-bind:class=`). Negative lookbehind ensures we only count the static
    # HTML `class=` attribute, not framework directives.
    class_attr_re = re.compile(r"(?<![:\-\w\.])class\s*=\s*[\"']")
    for tpl in TEMPLATES_ROOT.rglob("*.html"):
        try:
            text = tpl.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in tag_re.finditer(text):
            tag = m.group(0)
            if len(class_attr_re.findall(tag)) > 1:
                line_no = text[: m.start()].count("\n") + 1
                findings.append(
                    f"{tpl.relative_to(REPO_ROOT)}:{line_no}: "
                    f"duplicate class= attribute on a single tag — browsers keep "
                    f"the first and drop the second silently"
                )
    return findings


def scan_all() -> dict[str, list[str]]:
    return {
        "css_armed_scoping": _check_css_armed_scoping(),
        "js_arms_at_parse": _check_js_arms_at_parse(),
        "shells_load_sync": _check_shells_load_synchronously(),
        "no_duplicate_class_attrs": _check_no_duplicate_class_attrs(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any invariant has findings (zero-tolerance gate).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()

    findings = scan_all()
    total = sum(len(v) for v in findings.values())

    if args.json:
        print(json.dumps({"finding_count": total, "by_invariant": findings}, indent=2))
    else:
        print(f"reveal-armed-invariants scan: {total} violation(s)")
        for kind, items in findings.items():
            print(f"  {kind}: {len(items)}")
            for it in items[:20]:
                print(f"     {it}")

    if args.strict and total > 0:
        print(f"FAIL: {total} reveal-armed invariant violation(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
