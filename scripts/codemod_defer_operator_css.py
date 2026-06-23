#!/usr/bin/env python3
"""Wave B codemod: defer non-first-paint CSS on the operator shells.

Operator shells (control_plane_skeleton / admin/base_site / base) load 60-93
render-blocking stylesheets with no deferral. This converts a CONSERVATIVE,
high-confidence set of NON-first-paint sheets (interaction overlays, bulk bars,
modals, feature-specific pages, pagination) to the non-blocking
`media="print" onload="this.media='all'"` pattern — first paint is unaffected
because none of these style above-the-fold content, and the browser stops
blocking render on them.

DELIBERATELY NOT deferred (would risk FOUC): design-tokens*, fonts, bootstrap,
structural shells, base grammar, design-system, ALL theme files, header, sidebar/
nav, tables/forms/cards, density, footers, responsive, cockpit skins, and
rmc-signature-motion.css (it DEFINES :root easing tokens consumed by blocking CSS). Also rmc-cp-copilot-grid-lock.css (sets the 3-column shell grid), rmc-cp-activity-tiers.css (above-fold landing ticker), rmc-collapsable.css (above-fold section heads) — all first-paint, kept blocking after an audit.

Filename-keyed (not line-keyed) so it is robust to concurrent edits elsewhere in
the shell. Idempotent: a link already carrying media=/onload= is skipped.
Fully reversible (remove the two added attributes).

Usage:
  python scripts/codemod_defer_operator_css.py            # dry-run
  python scripts/codemod_defer_operator_css.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SHELLS = [
    "templates/control_plane_skeleton.html",
    "templates/admin/base_site.html",
    "templates/base.html",
]

# High-confidence NON-first-paint sheets (basenames). Each styles content that is
# hidden until interaction, or belongs to a specific feature/page, or sits below
# the fold — so deferring cannot flash visible above-the-fold content.
DEFER = {
    "rmc-command-bar.css",              # ⌘K palette overlay (display:none until opened)
    "rmc-admin-modal-overlay-guard.css",  # modal overlay (hidden)
    "rmc-bulk-actions.css",            # bulk action bar (appears on row select)
    "rmc-list-bulk-select.css",        # bulk select chrome (interaction)
    "rmc-workflow-progress.css",       # workflow-specific surface
    "rmc-workflow-guidance.css",       # workflow-specific surface
    "migration-cloud-ui.css",          # migration-cloud pages only
    "rmc-trust-pillars.css",           # specific marketing-style section
    "rmc-account-security-chip.css",   # specific chip widget
    "rmc-ai-guided-assistant-card.css",  # specific assistant card
    "rmc-pagination-grammar.css",      # pager (below the fold, end of lists)
    "rmc-admin-changelist-live.css",   # admin changelist live-update chrome (layers on the table)
}
# Deliberately NOT deferred even though tempting — they style PRIMARY page content
# and would flash unstyled: rmc-signup-form.css (the signup form itself),
# rmc-data-viz.css (charts can sit above the fold), admin-platform-catalog.css
# (the catalog grid IS the page).

# A <link rel="stylesheet" ...> for a given css basename that has NO media= yet.
def link_re(basename: str) -> re.Pattern:
    esc = re.escape(basename)
    return re.compile(
        r'(<link\s+rel="stylesheet"\s+href="\{%\s*static\s+\'css/' + esc + r"'\s*%\}\")"
        r"(?![^>]*\bmedia=)(?![^>]*\bonload=)"
        r"(\s*/?>)",
    )

DEFER_ATTRS = ' media="print" onload="this.media=\'all\'"'


def process(text: str) -> tuple[str, list[str]]:
    hits: list[str] = []
    for base in sorted(DEFER):
        pat = link_re(base)
        new, n = pat.subn(r"\1" + DEFER_ATTRS + r"\2", text)
        if n:
            hits.append(f"{base} ({n})")
            text = new
    return text, hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total = 0
    for rel in SHELLS:
        p = REPO / rel
        if not p.exists():
            print(f"  MISSING {rel}")
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        new, hits = process(src)
        deferred = sum(int(h.split("(")[1].rstrip(") ")) for h in hits)
        total += deferred
        print(f"{rel}: deferred {deferred} sheet(s)" + (": " + ", ".join(hits) if hits else ""))
        if args.apply and new != src:
            p.write_text(new, encoding="utf-8")

    print(f"\n{'APPLIED' if args.apply else 'DRY-RUN'}: {total} stylesheet(s) deferred across {len(SHELLS)} shells")
    return 0


if __name__ == "__main__":
    sys.exit(main())
