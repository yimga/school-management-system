#!/usr/bin/env python3
"""
Page fold standards — shells wire back-to-top + fold assets; task pages mark paginate policy.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "page_fold_standards_audit.json"


@dataclass
class Row:
    check_id: str
    description: str
    status: str
    proof: str


def _read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    rows: list[Row] = []

    def add(check_id: str, description: str, ok: bool, proof: str) -> None:
        rows.append(Row(check_id, description, "PASS" if ok else "FAIL", proof))

    shell_checks = [
        ("templates/portal_base.html", "back_to_top.html", "rmc-page-fold-standards"),
        ("templates/control_plane_skeleton.html", "back_to_top.html", "rmc-page-fold-standards"),
        ("templates/portal_base.html", 'data-rmc-page-fold-nav="required"', "manager"),
        ("templates/control_plane_base.html", 'data-rmc-page-fold-nav="required"', "cp-page-body"),
    ]
    for item in shell_checks:
        rel, needle, label = item[0], item[1], item[2]
        text = _read(rel)
        if label in ("rmc-page-fold-standards",):
            add(
                f"shell_{rel.replace('/', '_')}_back_to_top",
                f"{rel} includes back-to-top",
                "back_to_top.html" in text,
                rel,
            )
            add(
                f"shell_{rel.replace('/', '_')}_fold_assets",
                f"{rel} loads page fold standards assets",
                "rmc-page-fold-standards" in text,
                rel,
            )
        else:
            add(
                f"shell_{rel.replace('/', '_')}_{label}",
                f"{rel} wires {needle!r}",
                needle in text,
                rel,
            )

    add(
        "scroll_container_js",
        "rmc-scroll-container.js exists",
        (ROOT / "static/js/rmc-scroll-container.js").is_file(),
        "static/js/rmc-scroll-container.js",
    )
    add(
        "fold_standards_js",
        "rmc-page-fold-standards.js exists",
        (ROOT / "static/js/rmc-page-fold-standards.js").is_file(),
        "static/js/rmc-page-fold-standards.js",
    )
    add(
        "fold_standards_css",
        "rmc-page-fold-standards.css exists",
        (ROOT / "static/css/rmc-page-fold-standards.css").is_file(),
        "static/css/rmc-page-fold-standards.css",
    )
    add(
        "cursor_rule",
        "Cursor rule documents fold standards",
        (ROOT / ".cursor/rules/runmycampus-page-fold-standards.mdc").is_file(),
        ".cursor/rules/runmycampus-page-fold-standards.mdc",
    )

    fc = _read("templates/siteconfig/feature_control_panel_content.html")
    add(
        "feature_control_fold_nav",
        "Feature control marks data-rmc-page-fold-nav=required",
        'data-rmc-page-fold-nav="required"' in fc,
        "feature_control_panel_content.html",
    )
    add(
        "feature_control_paginate_policy",
        "Feature control marks data-rmc-scroll-policy=paginate",
        'data-rmc-scroll-policy="paginate"' in fc,
        "feature_control_panel_content.html",
    )
    add(
        "feature_control_sticky_tabs",
        "Feature control category tabs are sticky nav",
        "rmc-page-fold-nav--sticky" in fc and "<nav" in fc,
        "feature_control_panel_content.html",
    )

    pagination_partial = _read("templates/components/pagination.html")
    add(
        "pagination_partial",
        "Shared numbered pagination partial exists",
        "page_obj.paginator.num_pages" in pagination_partial,
        "components/pagination.html",
    )

    back_js = _read("static/js/_pages/components__back_to_top.js")
    add(
        "back_to_top_two_fold_threshold",
        "Back-to-top uses 2-fold scroll threshold",
        "fold * 2" in back_js or "scrollThreshold = fold * 2" in back_js,
        "components__back_to_top.js",
    )

    failed = [r for r in rows if r.status == "FAIL"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pass": len(failed) == 0,
        "rows": [asdict(r) for r in rows],
    }
    if args.write:
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        GENERATED.write_text(
            __import__("json").dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    for row in rows:
        print(f"[{row.status}] {row.check_id}: {row.description}")
    print(f"\nPAGE_FOLD_STANDARDS: {len(rows) - len(failed)}/{len(rows)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
