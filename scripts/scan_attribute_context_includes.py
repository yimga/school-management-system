"""Scan: detect `{% include %}` used INSIDE a tag's attribute list whose partial
emits a top-level HTML element.

Why this gate exists (2026-06-16):
    Several /super/ pages build an opening tag like

        <div id="...-main" ... {% include "schools/partials/decision_architecture_attrs.html" %} data-x="1">

    where the included partial is meant to emit ONLY `data-*` attributes. A bulk
    "add empty-state sentinel" sweep had appended a block-level
    `<div class="rmc-empty-state-sentinel">` to that attribute-only partial.
    Rendered INSIDE an opening tag, that element corrupts the parse: the host
    `<div>` never opens correctly, its later `</div>` closes an ancestor
    (`.rmc-app-shell`) early, and everything after it (the copilot rail, the
    footer) is hoisted out to <body>. The bug is POSITIONAL (an element in
    attribute context), so it passed static tag-balance AND the template
    render-safety gate, and only showed up as a broken layout in the browser.

    This gate seals that class: an `{% include %}` sitting between `<tag` and the
    next `>` (attribute context) must resolve to a partial that emits NO HTML
    element — attributes / `{% %}` / `{{ }}` / comments / whitespace only.

Detection:
  * Attribute-context include = a `<tagname ... {% include "PATH" %}` match with no
    `>` between the tag-open and the include (the `[^>]*` in the regex).
  * The partial "emits an element" if, after stripping `{% comment %}…%}`,
    `{# … #}` and `<!-- … -->`, it still contains an HTML element open token
    (`<` followed by an ASCII letter). Conditional elements (inside `{% if %}`)
    count — they still render when the branch is taken.

Resolution:
  * Quoted include paths only (`{% include "a/b.html" %}`); variable includes are
    skipped (cannot resolve statically). Paths resolve under the project
    `templates/` dir, with a recursive fallback search for app-local template
    dirs. Unresolvable paths are reported as a soft note, never a hard failure.

Usage:
    python scripts/scan_attribute_context_includes.py [--json]
Exit 1 on any violation (baseline 0), else 0.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES_ROOT = REPO_ROOT / "templates"

# `<tag` ... (no `>`) ... `{% include "PATH" %}`  — include inside an opening tag.
ATTR_CTX_INCLUDE_RE = re.compile(
    r"<[a-zA-Z][a-zA-Z0-9]*[^>]*?\{%\s*include\s+\"([^\"]+)\"",
)
# Any HTML element open token (after comments are stripped).
ELEMENT_OPEN_RE = re.compile(r"<[a-zA-Z]")


def _strip_comments(text: str) -> str:
    text = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", text, flags=re.DOTALL)
    text = re.sub(r"\{#.*?#\}", "", text, flags=re.DOTALL)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return text


def _resolve_partial(include_path: str) -> pathlib.Path | None:
    direct = TEMPLATES_ROOT / include_path
    if direct.is_file():
        return direct
    # Fallback: app-local template dirs (apps/<app>/templates/<path>).
    matches = list(REPO_ROOT.glob(f"**/templates/{include_path}"))
    return matches[0] if matches else None


def _partial_emits_element(path: pathlib.Path) -> bool:
    try:
        body = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return False
    return bool(ELEMENT_OPEN_RE.search(body))


def scan_all() -> tuple[list[str], list[str]]:
    violations: list[str] = []
    soft_notes: list[str] = []
    for path in sorted(TEMPLATES_ROOT.rglob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in ATTR_CTX_INCLUDE_RE.finditer(text):
            include_path = m.group(1)
            line_no = text.count("\n", 0, m.start()) + 1
            partial = _resolve_partial(include_path)
            rel = path.relative_to(REPO_ROOT)
            if partial is None:
                soft_notes.append(f"{rel}:{line_no}: unresolved include '{include_path}' (skipped)")
                continue
            if _partial_emits_element(partial):
                violations.append(
                    f"{rel}:{line_no}: attribute-context include '{include_path}' "
                    f"emits a top-level element (must be attributes-only)"
                )
    return violations, soft_notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    violations, soft_notes = scan_all()

    if args.json:
        print(json.dumps({"finding_count": len(violations), "findings": violations,
                          "soft_notes": soft_notes}, indent=2))
    else:
        print(f"attribute-context-include scan: {len(violations)} violation(s)")
        print("baseline: 0")
        for v in violations:
            print(f"  {v}")
        if soft_notes:
            print(f"({len(soft_notes)} unresolved include(s) skipped)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
