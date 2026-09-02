#!/usr/bin/env python3
"""Wire data-rmc-row-detail-table (+ auto scrape) on templates using rmc-data-table.

This script used to do a second thing: `_ensure_glocal_tags` appended
`glocal_tags` to each patched template's first `{% load %}` line.  That is
where the 102 templates carrying a `{% load glocal_tags %}` they never use
came from -- apps/platform_runtime/templatetags/glocal_tags.py registers ONE
tag, `glocal_token`, and no template in the repo calls it.  The load was
written to satisfy a check in verify_glocal_adoption_tranche that asked
whether the WORD appeared; that check now asserts use instead, so injecting
the line would only manufacture more dead source.  Adopting the lexicon means
calling the tag, which is a decision per template, not a codemod.

It also rewrote every patched file with `newline="\n"`.  Templates in this
repo are committed CRLF, so a two-attribute edit came back as a whole-file
diff.  Line endings are now preserved as found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

EXCLUDE_REL = frozenset(
    {
        "templates/portal_base.html",
        "templates/control_plane_skeleton.html",
        "templates/admin/base_site.html",
        "templates/base.html",
        "templates/customersuccess/guided_onboarding.html",
        "templates/siteconfig/partials/reportcard_style_preview_body.html",
        "templates/admin/partials/admin_v1_index_surface_previews.html",
        "templates/partials/cockpit/_churn_scorecard.html",
        "templates/components/rmc_skeleton.html",
    }
)

TABLE_OPEN_RE = re.compile(
    r"<table\b(?P<attrs>[^>]*\brmc-data-table\b[^>]*)>",
    re.IGNORECASE,
)
def _patch_table_opener(match: re.Match[str], *, use_auto: bool) -> str:
    attrs = match.group("attrs")
    if "data-rmc-row-detail-table" not in attrs:
        attrs = attrs.rstrip() + ' data-rmc-row-detail-table="1"'
    if use_auto and "data-rmc-row-detail-auto" not in attrs:
        attrs = attrs.rstrip() + ' data-rmc-row-detail-auto="1"'
    return f"<table{attrs}>"


def patch_file(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in EXCLUDE_REL:
        return False
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if "rmc-data-table" not in text:
        return False
    use_auto = 'data-rmc-row-detail="1"' not in text and "data-rmc-row-detail='1'" not in text
    new_text = TABLE_OPEN_RE.sub(
        lambda m: _patch_table_opener(m, use_auto=use_auto),
        text,
    )
    if new_text == text:
        return False
    # Write bytes, not text: newline="\n" normalised every CRLF
    # template it touched, turning a two-attribute edit into a whole-file diff.
    path.write_bytes(new_text.encode("utf-8"))
    return True


def main() -> int:
    changed: list[str] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        if patch_file(path):
            changed.append(path.relative_to(ROOT).as_posix())
    print(f"apply_glocal_row_detail_auto: patched {len(changed)} template(s)")
    for rel in changed[:20]:
        print(f"  - {rel}")
    if len(changed) > 20:
        print(f"  ... and {len(changed) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
