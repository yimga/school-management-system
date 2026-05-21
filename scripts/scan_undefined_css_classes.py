#!/usr/bin/env python3
"""Detect CSS class names referenced in templates that have no corresponding
CSS rule anywhere in the project.

Caught `content-max-960` (referenced 25x, never defined -> silent layout bug).

Strategy:
  1. Parse every project CSS file -> extract every selector that contains a
     class fragment (`.foo` patterns inside selectors, including
     `.foo[attr]`, `.foo.bar`, `.foo > .bar`, etc.).
  2. Parse every template `class="..."` attribute -> extract class tokens.
  3. Allow Bootstrap utility classes (`d-flex`, `mt-2`, `col-lg-*`, `row`,
     `nav-*`, etc.) since those live in the vendored bootstrap stylesheet.
  4. Allow JS-generated classes by sniffing `static/js/**/*.js` for class
     literals that match.
  5. Report any template-referenced class that doesn't appear in any CSS or
     JS source — these are dead references or undefined utilities.

Drift-detection scanner with `--compare` for CI parity.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS_SCAN_ROOTS = [
    ROOT / "static",  # all CSS under static, including subdirs like static/marketing/css
]
JS_ROOT = ROOT / "static" / "js"
TEMPLATES_ROOT = ROOT / "templates"
BASELINE = ROOT / "var" / "security-audit-baseline-undefined-css-classes.json"

# Bootstrap utility / framework class prefixes that we accept as "defined"
# without grepping the vendored CSS (~25k classes — too noisy).
BOOTSTRAP_PREFIXES = (
    "container", "container-fluid", "row", "col", "g-", "gx-", "gy-",
    "m-", "mt-", "mb-", "ms-", "me-", "mx-", "my-",
    "p-", "pt-", "pb-", "ps-", "pe-", "px-", "py-",
    "d-", "flex-", "justify-", "align-",
    "text-", "fw-", "fst-", "fs-", "lh-",
    "bg-", "border", "rounded",
    "h-", "w-", "vh-", "vw-", "mh-", "mw-",
    "btn", "card", "nav", "navbar", "modal", "dropdown", "alert", "badge",
    "list-group", "form-", "input-", "table", "spinner-",
    "shadow", "opacity-",
    "position-", "top-", "bottom-", "start-", "end-",
    "fa-", "bi-",          # icon font classes
    "visually-hidden", "sr-only", "stretched-link",
    "active", "show", "fade", "collapse", "collapsing", "in",
    "carousel-", "tooltip", "popover", "toast",
    "offcanvas", "ratio", "object-fit-", "user-select-",
    "z-",
)
# Single literal classes that are framework-supplied or runtime semantics.
BOOTSTRAP_LITERALS = frozenset({
    "container", "row", "active", "show", "fade", "open", "selected",
    "is-invalid", "is-valid", "was-validated",
    "htmx-indicator", "htmx-request", "htmx-settling", "htmx-swapping",
    "fixed", "sticky", "ratio", "shadow", "blockquote", "lead",
    "small", "h1", "h2", "h3", "h4", "h5", "h6", "display-1", "display-2",
    "display-3", "display-4", "display-5", "display-6",
    "img-fluid", "img-thumbnail", "figure", "figure-img", "figure-caption",
    "table-responsive", "table-sm", "table-bordered", "table-striped",
    "table-hover", "table-dark", "table-light",
})

# Skip these template dirs (third-party / vendor).
EXCLUDE_PARTS = {"node_modules", "staticfiles", ".git", "venv", ".venv",
                 "vendor", "unfold"}

CLASS_TOKEN = re.compile(r'class\s*=\s*(["\'])([^"\']*?)\1')
DJANGO_TAG = re.compile(r"\{[%{].*?[%}]\}")
SELECTOR_CLASS = re.compile(r"\.([A-Za-z_][\w-]*)")


def _is_bootstrap(cls: str) -> bool:
    if cls in BOOTSTRAP_LITERALS:
        return True
    return any(cls.startswith(p) for p in BOOTSTRAP_PREFIXES)


# Classes worth catching are the ones whose typos hide real bugs — project-prefixed
# layout / component classes. Tailwind / Unfold / email-only utilities are noise.
INTENTIONAL_PREFIXES = (
    "rmc-", "cp-", "mkt-", "marketing-",
    "portal-", "control-plane-", "dashboard-", "manager-",
    "tenant-", "studio-", "site-", "page-", "ccc-",
    "feature-", "wedge-", "wizard-", "report-", "school-",
    "finance-", "evals-", "ds-", "ai-", "setup-studio-",
    "content-max-",  # the bug class that motivated this scanner
)


def _is_intentional_project_class(cls: str) -> bool:
    return any(cls.startswith(p) for p in INTENTIONAL_PREFIXES)


def collect_defined_classes() -> set[str]:
    defined: set[str] = set()
    # From CSS files under every scan root (static/css, static/marketing/css, etc.)
    for css_root in CSS_SCAN_ROOTS:
        for p in css_root.rglob("*.css"):
            if any(part in EXCLUDE_PARTS for part in p.parts):
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            # Strip comments so commented-out selectors don't count
            text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
            for m in SELECTOR_CLASS.finditer(text):
                defined.add(m.group(1))
    # From JS files (classes added via classList.add / className = ...)
    js_class_literal = re.compile(r"""classList\.(?:add|toggle|remove)\s*\(\s*["']([^"']+)["']""")
    re.compile(r"""["']([\w-]+)["']\s*(?:,|\))""")
    for p in JS_ROOT.rglob("*.js"):
        if any(part in EXCLUDE_PARTS for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            continue
        for m in js_class_literal.finditer(text):
            for cls in m.group(1).split():
                defined.add(cls)
        # Cheap heuristic — strings used near class assignment.
        for m in re.finditer(r"(?:className|class)\s*[+=]\s*([\"'])([^\"']+)\1", text):
            for cls in m.group(2).split():
                if cls and not cls.startswith(("/", "<", "{")):
                    defined.add(cls)
    return defined


def collect_template_class_uses() -> dict[str, list[tuple[Path, int]]]:
    uses: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for p in TEMPLATES_ROOT.rglob("*.html"):
        if any(part in EXCLUDE_PARTS for part in p.parts):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in CLASS_TOKEN.finditer(text):
            body = m.group(2)
            # Strip Django tags inside class attribute (e.g. `{% if foo %}bar{% endif %}`)
            body = DJANGO_TAG.sub(" ", body)
            line = text.count("\n", 0, m.start()) + 1
            for tok in body.split():
                tok = tok.strip()
                if not tok or tok.startswith(("{", "}")):
                    continue
                # Strip any leftover punctuation
                tok = tok.lstrip(".").strip()
                if tok:
                    uses[tok].append((p, line))
    return uses


def collect_undefined() -> list[dict]:
    defined = collect_defined_classes()
    uses = collect_template_class_uses()
    undefined: list[dict] = []
    for cls, refs in uses.items():
        if _is_bootstrap(cls):
            continue
        if cls in defined:
            continue
        if cls[0].isdigit():
            continue
        # BEM-separator residue from template substitution like
        # `studio-os__{{ workspace_mode }}-rail` -> `studio-os__` after stripping
        # `{{ ... }}`. Real BEM classes never end on a bare separator.
        if cls.endswith(("__", "--")):
            continue
        # Drop Tailwind / Unfold / email-only utilities — too noisy and not the
        # bug class this scanner is for. Only project-prefixed classes here.
        if not _is_intentional_project_class(cls):
            continue
        undefined.append({
            "class": cls,
            "uses": len(refs),
            "first_file": str(refs[0][0].relative_to(ROOT).as_posix()),
            "first_line": refs[0][1],
        })
    undefined.sort(key=lambda r: -r["uses"])
    return undefined


def write_baseline(undefined: list[dict]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scanner": "undefined-css-classes",
        "total": len(undefined),
        "total_uses": sum(r["uses"] for r in undefined),
        "findings": undefined,
    }
    BASELINE.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_baseline() -> dict:
    if not BASELINE.exists():
        return {"findings": [], "total": 0}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()

    undefined = collect_undefined()

    if args.write_baseline:
        write_baseline(undefined)
        print(f"Wrote baseline: {len(undefined)} undefined class(es), {sum(r['uses'] for r in undefined)} total reference(s)")
        for r in undefined[:20]:
            print(f"  {r['uses']:>3}x  .{r['class']}  ({r['first_file']}:{r['first_line']})")
        return 0

    if args.compare:
        base = load_baseline()
        {(r["class"], r["uses"]) for r in base.get("findings", [])}
        {(r["class"], r["uses"]) for r in undefined}
        # CI fails when a new undefined class appears OR usage of one grows.
        new_classes = {r["class"] for r in undefined} - {r["class"] for r in base.get("findings", [])}
        if new_classes:
            print(f"FAIL: {len(new_classes)} new undefined CSS class(es) introduced:")
            for r in undefined:
                if r["class"] in new_classes:
                    print(f"  NEW: .{r['class']} — {r['uses']}x — first at {r['first_file']}:{r['first_line']}")
            return 1
        print(f"PASS: undefined CSS classes {base.get('total', 0)} -> {len(undefined)} (no new classes)")
        return 0

    # Default informational report
    print(f"Undefined CSS class names referenced in templates: {len(undefined)}")
    print(f"Total reference count: {sum(r['uses'] for r in undefined)}")
    for r in undefined[:30]:
        print(f"  {r['uses']:>3}x  .{r['class']}  ({r['first_file']}:{r['first_line']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
