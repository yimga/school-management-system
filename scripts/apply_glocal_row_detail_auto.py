#!/usr/bin/env python3
"""Wire data-rmc-row-detail-table (+ auto scrape) on templates using rmc-data-table."""

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
LOAD_RE = re.compile(r"(\{%\s*load\s+)([^%]+?)(\s*%\})")


def _patch_table_opener(match: re.Match[str], *, use_auto: bool) -> str:
    attrs = match.group("attrs")
    if "data-rmc-row-detail-table" not in attrs:
        attrs = attrs.rstrip() + ' data-rmc-row-detail-table="1"'
    if use_auto and "data-rmc-row-detail-auto" not in attrs:
        attrs = attrs.rstrip() + ' data-rmc-row-detail-auto="1"'
    return f"<table{attrs}>"


def _ensure_glocal_tags(content: str) -> str:
    if "glocal_tags" in content:
        return content
    load = LOAD_RE.search(content)
    if not load:
        return content
    tags = load.group(2).strip()
    if "glocal_tags" in tags:
        return content
    new_tags = f"{tags} glocal_tags"
    return content[: load.start(2)] + new_tags + content[load.end(2) :]


def patch_file(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in EXCLUDE_REL:
        return False
    text = path.read_text(encoding="utf-8")
    if "rmc-data-table" not in text:
        return False
    use_auto = 'data-rmc-row-detail="1"' not in text and "data-rmc-row-detail='1'" not in text
    new_text = TABLE_OPEN_RE.sub(
        lambda m: _patch_table_opener(m, use_auto=use_auto),
        text,
    )
    new_text = _ensure_glocal_tags(new_text)
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8", newline="\n")
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
