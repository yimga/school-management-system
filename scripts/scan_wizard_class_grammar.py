#!/usr/bin/env python
"""scan_wizard_class_grammar.py — zero-tolerance gate (baseline 0).

Every ``.rmc-wizard-*`` class referenced in
``templates/setup_studio/**.html`` MUST be defined in
``static/css/rmc-wizard.css`` or ``static/css/rmc-class-grammar.css``.

Mirrors ``scan_undefined_css_classes.py``; narrowly-scoped to the wizard
class grammar to keep the wizard layer self-contained.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TEMPLATE_DIR = REPO_ROOT / "templates" / "setup_studio"
CSS_FILES = [
    REPO_ROOT / "static" / "css" / "rmc-wizard.css",
    REPO_ROOT / "static" / "css" / "rmc-class-grammar.css",
]

# Match class="..." occurrences and extract .rmc-wizard-... tokens
_CLASS_ATTR_RE = re.compile(r'class\s*=\s*["\']([^"\']*)["\']')
_RMC_WIZARD_TOKEN_RE = re.compile(r'(rmc-wizard-[a-z0-9_-]+)')
_CSS_SELECTOR_RE = re.compile(r'\.([a-z][a-z0-9_-]*)')


def collect_referenced_classes() -> set[str]:
    seen: set[str] = set()
    if not TEMPLATE_DIR.exists():
        return seen
    for path in TEMPLATE_DIR.rglob("*.html"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for attr_match in _CLASS_ATTR_RE.finditer(text):
            for tok in _RMC_WIZARD_TOKEN_RE.findall(attr_match.group(1)):
                seen.add(tok)
    return seen


def collect_defined_classes() -> set[str]:
    seen: set[str] = set()
    for path in CSS_FILES:
        if not path.exists():
            continue
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
    defined = collect_defined_classes()
    missing = sorted(referenced - defined)
    if missing:
        print(f"\nFAILED — {len(missing)} undefined .rmc-wizard-* class(es) referenced in templates:")
        for cls in missing:
            print(f"  - {cls}")
        return 1
    print(f"\nscan_wizard_class_grammar: PASS ({len(referenced)} class refs, all defined)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
