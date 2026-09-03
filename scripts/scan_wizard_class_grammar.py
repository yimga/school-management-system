#!/usr/bin/env python
"""scan_wizard_class_grammar.py -- zero-tolerance gate (baseline 0).

Every ``.rmc-wizard-*`` class referenced in ``templates/setup_studio/**.html``
must be defined in a stylesheet those pages actually LOAD.

Why this was rewritten (2026-09-02)
-----------------------------------
``CSS_FILES`` was a hardcoded list of two paths -- ``rmc-wizard.css`` and
``rmc-class-grammar.css``. The wizard CSS has since been split across more
sheets, and half of what a wizard page loads comes from the shell it extends.
The gate was told none of this.

So it reported **13 undefined classes, and 12 of them were false**. The seven
``rmc-wizard-assist__*`` classes live in ``rmc-wizard-assist.css``;
``rmc-wizard-card__desc`` and ``rmc-wizard-index-grid`` live in
``rmc-wizard-index.css``; three ``rmc-wizard-zf-*`` classes live in
``rmc-tenant-activation-surfaces.css``, which ``templates/portal_base.html``
links and no wizard template does.

That is worse than a gate that merely misses things. This one is wired into CI
(``architectural-boundaries.yml``) with a ZERO baseline, so it stood red against
``main`` for a defect that was 92% imaginary -- and the one REAL finding in its
output was buried in the noise. A gate that cries wolf gets switched off, and
the true finding rides back in behind it.

What it was hiding: ``rmc-wizard-zf-preview__item--muted`` is rendered on all
six items of ``wizard_migration_scope_preview.html`` and toggled by
``rmc-wizard-zero-friction-scope.js`` as the exact inverse of ``--ready`` -- but
only ``--ready`` was ever styled, so the "not yet unlocked" half of a two-state
control had no visual state at all.

The fix applies this gate's own principle to itself: resolve the BEHAVIOUR
(which stylesheets does this page load) instead of asserting a WORD (a filename
somebody typed once). A wizard stylesheet added tomorrow is covered
automatically, and a class defined only in some sheet no wizard page loads still
fails -- which a "just search all of static/css" fix would have let through.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TEMPLATE_DIR = REPO_ROOT / "templates" / "setup_studio"
STATIC_ROOT = REPO_ROOT / "static"

# Match class="..." occurrences and extract .rmc-wizard-... tokens
_CLASS_ATTR_RE = re.compile(r'class\s*=\s*["\']([^"\']*)["\']')
_RMC_WIZARD_TOKEN_RE = re.compile(r'(rmc-wizard-[a-z0-9_-]+)')
_CSS_SELECTOR_RE = re.compile(r'\.([a-z][a-z0-9_-]*)')

#: ``{% static 'css/foo.css' %}`` -- how a template names a stylesheet here.
_STATIC_CSS_RE = re.compile(r'\{%\s*static\s+["\']([^"\']+\.css)["\']\s*%\}')

#: ``{% extends "portal_base.html" %}`` -- the shell that owns the <head>.
_EXTENDS_RE = re.compile(r'\{%\s*extends\s+["\']([^"\']+)["\']\s*%\}')


def _templates() -> list[Path]:
    if not TEMPLATE_DIR.exists():
        return []
    return sorted(TEMPLATE_DIR.rglob("*.html"))


def collect_referenced_classes() -> set[str]:
    seen: set[str] = set()
    for path in _templates():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for attr_match in _CLASS_ATTR_RE.finditer(text):
            for tok in _RMC_WIZARD_TOKEN_RE.findall(attr_match.group(1)):
                seen.add(tok)
    return seen


def _extended_shells() -> set[str]:
    """The shells the wizard templates extend -- discovered, not assumed."""
    shells: set[str] = set()
    for path in _templates():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for name in _EXTENDS_RE.findall(text):
            rel = "templates/" + name.lstrip("/")
            if (REPO_ROOT / rel).is_file():
                shells.add(rel)
    return shells


def collect_linked_stylesheets() -> list[Path]:
    """Every stylesheet a wizard page actually loads.

    Two sources, both DERIVED -- no filename is hardcoded, which is the point:

      1. ``{% static 'css/x.css' %}`` written in the wizard templates.
      2. Everything the shells they ``{% extends %}`` deliver. This half is what
         the old two-file list could never see.

    Shell resolution is delegated to ``shell_css_contract`` -- the repo's own
    resolver, which follows ``{% extends %}`` and ``{% include %}``, honours
    ``{% if False %}``, and credits a rule delivered through a bundle. A second
    opinion here is how two halves of one contract drift apart.

    LIMIT, stated rather than hidden: this is a UNION across the wizard layer,
    not a per-page answer, so a class defined only in a sheet one shell loads
    counts for a page rendered on the other. Tightening that needs include-graph
    resolution for partials -- most of these templates ARE partials, whose
    stylesheets depend on whoever includes them -- and would trade a broad class
    of false positives for a narrow true one. The union is the honest bound.
    """
    rels: set[str] = set()
    for path in _templates():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rels |= set(_STATIC_CSS_RE.findall(text))

    names: set[str] = {Path(r).name for r in rels}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import shell_css_contract as scc

        for shell in sorted(_extended_shells()):
            names |= set(scc.linked_stylesheets(shell, depth=3))
    except Exception as exc:  # pragma: no cover
        # A resolver that silently finds nothing would report every
        # shell-delivered class undefined. Say so loudly rather than emit a
        # confident wrong list.
        print(
            "  WARNING: shell resolution unavailable (%s: %s); shell-delivered "
            "stylesheets will read as undefined" % (type(exc).__name__, exc),
            file=sys.stderr,
        )

    out: list[Path] = []
    for css_root in (STATIC_ROOT / "css", STATIC_ROOT / "marketing" / "css"):
        if not css_root.is_dir():
            continue
        for p in sorted(css_root.rglob("*.css")):
            if p.name in names:
                out.append(p)
    return out


def collect_defined_classes(css_files: list[Path]) -> set[str]:
    seen: set[str] = set()
    for path in css_files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for tok in _CSS_SELECTOR_RE.findall(text):
            if tok.startswith("rmc-wizard-"):
                seen.add(tok)
    return seen


def main(argv: list[str]) -> int:
    print("== scan_wizard_class_grammar (baseline 0) ==")
    referenced = collect_referenced_classes()
    css_files = collect_linked_stylesheets()

    if not css_files:
        # A resolver that finds nothing would call every class undefined. That
        # is a broken detector, not a clean tree.
        print(
            "\nFAILED -- the wizard templates resolve to no stylesheet at all. "
            "Either the {% static %}/{% extends %} forms changed or the "
            "templates moved; fix the resolver, do not trust its findings.",
            file=sys.stderr,
        )
        return 1

    defined = collect_defined_classes(css_files)
    missing = sorted(referenced - defined)

    print(
        "  %d class ref(s); resolved %d stylesheet(s) the wizard layer loads"
        % (len(referenced), len(css_files))
    )

    if missing:
        print(
            "\nFAILED -- %d .rmc-wizard-* class(es) referenced in a template and "
            "defined in NONE of the stylesheets those pages load:" % len(missing)
        )
        for cls in missing:
            print(f"  - {cls}")
        return 1
    print(f"\nscan_wizard_class_grammar: PASS ({len(referenced)} class refs, all defined)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
