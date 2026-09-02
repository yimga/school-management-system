#!/usr/bin/env python3
"""Gate: manager marketplace control-plane pages use compact surface + paginate policy.

Page-fold nav
-------------
This gate used to require the literal string ``rmc-cp-compact__fold-nav`` in
each page's own bytes.  All six pages did carry it once (ced2c2601), and then
two deliberate migrations moved it:

  f35fffafa  replaced the bespoke sticky nav with a curated
             ``rmc-section-nav--toc`` TOC;
  d7b55fe85  "Replace sticky section TOC with static inline jumps across
             operator and tenant surfaces" -- the jump list became
             ``jump_a_id``/``jump_a_label`` ... kwargs handed to
             ``components/rmc_operational_center_frame.html``, which renders
             them as an ``aria-label="Jump to section"`` toolbar of
             ``rmc-ops-frame__jump`` anchors.

So the nav is on every one of these pages; the ASSERTION was left pointing at
a class name the repo retired, one include shallower than the markup that
replaced it.  The check now asks whether a jump-to-section nav is actually
delivered -- inline, or through the shared frame -- and additionally that
every target it names resolves to a real ``id`` in the page's content tree,
which the class-name test could never have noticed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "marketplace"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shell_css_contract as css_contract  # noqa: E402  (repo-local helper)

REQUIRED = (
    "app_catalog.html",
    "governance_console.html",
    "blueprint_marketplace.html",
    "compatibility_matrix.html",
    "sandbox_inspector.html",
    "installation_health.html",
)

#: Matched as plain substrings -- an attribute value and an include path.
LITERAL_MARKERS = (
    'data-rmc-scroll-policy="paginate"',
    "components/pagination.html",
)

#: Matched as WHOLE class tokens.  `"rmc-cp-compact" in text` is also true of
#: `rmc-cp-compact__stat`, so a page could drop the compact surface class from
#: its container and still satisfy the check on a BEM child of it.
CLASS_MARKERS = ("rmc-cp-compact",)

#: Literal jump targets handed to components/rmc_operational_center_frame.html.
_JUMP_ID = re.compile(r'jump_[a-z]_id\s*=\s*"([^"]+)"')
#: A fold nav written inline on the page instead of through the shared frame.
_INLINE_FOLD_NAV = re.compile(r'class="[^"]*rmc-(?:cp-compact__fold-nav|page-fold-nav)[^"]*"')
_INLINE_ANCHOR = re.compile(r'href="#([^"]+)"')
_ELEMENT_ID = re.compile(r'\bid="([^"]+)"')

FRAME = "rmc_operational_center_frame.html"


def _has_class(text: str, name: str) -> bool:
    """True when *name* appears as a whole class token, not as a BEM prefix."""
    return re.search(re.escape(name) + r"(?![\w-])", text) is not None


def _fold_nav_failures(name: str, rel: str) -> list[str]:
    """Findings for the page-fold nav on one control-plane page."""
    own = css_contract.reachable_text(rel)
    content = css_contract.content_text(rel)
    ids = set(_ELEMENT_ID.findall(content))

    targets = sorted(set(_JUMP_ID.findall(own)))
    via = f"{FRAME} jump targets"
    if not targets:
        inline = _INLINE_FOLD_NAV.search(own)
        if inline:
            targets = sorted(set(_INLINE_ANCHOR.findall(own)))
            via = "inline fold nav"

    out: list[str] = []
    if len(targets) < 2:
        out.append(
            f"{name}: no page-fold nav -- pass at least two jump_<x>_id/"
            f"jump_<x>_label pairs to {FRAME}, or write an inline "
            f"rmc-cp-compact__fold-nav with two or more anchors"
        )
        return out
    if via.startswith(FRAME) and not css_contract.renders(rel, FRAME):
        out.append(
            f"{name}: names jump targets {targets} but never renders {FRAME}, "
            f"so nothing draws them"
        )
    for target in targets:
        if target not in ids:
            out.append(
                f"{name}: page-fold nav ({via}) points at #{target}, "
                f"which is not an id on the page"
            )
    return out


def main() -> int:
    failures: list[str] = []
    for name in REQUIRED:
        path = TEMPLATES / name
        if not path.is_file():
            failures.append(f"missing template: {path.relative_to(ROOT)}")
            continue
        rel = f"templates/marketplace/{name}"
        # Reachable text, not raw bytes: a marker parked behind {% if False %}
        # or inside {% comment %} is still spelled in the file.
        text = css_contract.reachable_text(rel)
        for marker in LITERAL_MARKERS:
            if marker not in text:
                failures.append(f"{name}: missing {marker}")
        for marker in CLASS_MARKERS:
            if not _has_class(text, marker):
                failures.append(f"{name}: missing class {marker}")
        failures.extend(_fold_nav_failures(name, rel))
    if failures:
        print("MARKETPLACE_CP_COMPACT_CONTRACT: FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"MARKETPLACE_CP_COMPACT_CONTRACT: PASS ({len(REQUIRED)} templates)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
