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
    parser.add_argument("--base", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    rows: list[Row] = []

    def add(check_id: str, description: str, ok: bool, proof: str) -> None:
        rows.append(Row(check_id, description, "PASS" if ok else "FAIL", proof))

    shell_checks = [
        ("templates/portal_base.html", "back_to_top.html", "rmc-page-fold-standards"),
        ("templates/control_plane_skeleton.html", "back_to_top.html", "rmc-page-fold-standards"),
        ("templates/base.html", "back_to_top.html", "rmc-page-fold-standards"),
        ("templates/marketing/base_marketing.html", "back_to_top.html", "rmc-page-fold-standards"),
        ("templates/admin/base.html", "back_to_top.html", "rmc-page-fold-standards"),
        ("templates/portal_base.html", 'data-rmc-page-fold-nav="required"', "manager"),
        ("templates/control_plane_base.html", 'data-rmc-page-fold-nav="required"', "cp-page-body"),
    ]
    for item in shell_checks:
        rel, needle, label = item[0], item[1], item[2]
        text = _read(rel)
        if label in ("rmc-page-fold-standards",):
            wired = (
                "back_to_top.html" in text
                or "rmc_platform_chrome_scripts.html" in text
            )
            add(
                f"shell_{rel.replace('/', '_')}_back_to_top",
                f"{rel} includes back-to-top",
                wired,
                rel,
            )
            add(
                f"shell_{rel.replace('/', '_')}_fold_assets",
                f"{rel} loads page fold standards assets",
                "rmc-page-fold-standards" in text
                or "rmc_platform_chrome_scripts.html" in text,
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
    cursorrules = _read(".cursorrules")
    cursor_doc = (ROOT / ".cursor/rules/runmycampus-page-fold-standards.mdc").is_file() or (
        "verify_page_fold_standards" in cursorrules
        and "page-fold" in cursorrules.lower()
    )
    add(
        "cursor_rule",
        "Fold standards documented (.cursor rule or tracked .cursorrules)",
        cursor_doc,
        ".cursorrules" if "verify_page_fold_standards" in cursorrules else ".cursor/rules/...",
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
        "feature_control_category_tabs",
        "Feature control category tabs present (static, not sticky)",
        "feature-cat-tabs" in fc and "<nav" in fc and "rmc-page-fold-nav--sticky" not in fc,
        "feature_control_panel_content.html",
    )

    admin_index = _read("templates/admin/index_superadmin.html")
    add(
        "admin_index_fold_nav",
        "Platform admin index marks data-rmc-page-fold-nav=required",
        'data-rmc-page-fold-nav="required"' in admin_index,
        "templates/admin/index_superadmin.html",
    )
    add(
        "admin_index_section_nav",
        "Platform admin index section jumps in unified hero toolbar",
        "cp-hero__actions-group--sections" in admin_index
        and "data-rmc-section-anchor" in admin_index,
        "templates/admin/index_superadmin.html",
    )
    add(
        "section_nav_toc_css",
        "Platform chrome loads section-nav TOC stylesheet",
        "rmc-section-nav-toc.css" in _read("templates/partials/rmc_platform_chrome_styles.html"),
        "templates/partials/rmc_platform_chrome_styles.html",
    )
    add(
        "admin_index_catalog_collapsed",
        "Platform admin catalog sections default collapsed (no open attribute)",
        "<details" in admin_index
        and 'data-rmc-admin-catalog-section' in admin_index
        and "<details class=\"rmc-admin-catalog-section\" id=" in admin_index,
        "templates/admin/index_superadmin.html",
    )

    pagination_partial = _read("templates/components/pagination.html")
    add(
        "pagination_partial",
        "Shared numbered pagination partial exists",
        "page_obj.paginator.num_pages" in pagination_partial,
        "components/pagination.html",
    )

    back_js = _read("static/js/_pages/components__back_to_top.js")
    back_tpl = _read("templates/components/back_to_top.html")
    add(
        "back_to_top_two_fold_threshold",
        "Back-to-top uses 2-fold scroll threshold",
        (
            "THRESHOLD_FOLDS = 2" in back_js
            or "fold * 2" in back_js
            or "foldHeight() * THRESHOLD_FOLDS" in back_js
        ),
        "components__back_to_top.js",
    )
    add(
        "back_to_top_scroll_container_first",
        "Back-to-top loads scroll-container before init",
        "rmc-scroll-container.js" in back_tpl
        and back_tpl.find("rmc-scroll-container.js")
        < back_tpl.find("components__back_to_top.js"),
        "components/back_to_top.html",
    )

    chrome_styles = _read("templates/partials/rmc_platform_chrome_styles.html")
    chrome_scripts = _read("templates/partials/rmc_platform_chrome_scripts.html")
    add(
        "chrome_collapsable_css",
        "Platform chrome loads rmc-collapsable.css (operator+tenant parity)",
        "rmc-collapsable.css" in chrome_styles,
        "rmc_platform_chrome_styles.html",
    )
    add(
        "chrome_collapsable_js",
        "Platform chrome loads rmc-collapsable.js after fold standards",
        "rmc-collapsable.js" in chrome_scripts
        and chrome_scripts.find("rmc-page-fold-standards.js")
        < chrome_scripts.find("rmc-collapsable.js"),
        "rmc_platform_chrome_scripts.html",
    )

    fold_js = _read("static/js/rmc-page-fold-standards.js")
    fold_css = _read("static/css/rmc-page-fold-standards.css")
    for needle, cid, desc in (
        ("initFoldStages", "fold_js_stages", "Fold JS implements fold stages"),
        ("initFieldsetAccordion", "fold_js_fieldset_accordion", "Fold JS implements fieldset accordion"),
        ("initCardStackPagination", "fold_js_card_pager", "Fold JS implements card-stack pager"),
        ("initSecondaryFolds", "fold_js_secondary_folds", "Fold JS implements secondary-fold collapse"),
        (".rmc-fold-stages", "fold_css_stages", "Fold CSS defines .rmc-fold-stages"),
    ):
        src = fold_css if needle.startswith(".") else fold_js
        add(cid, desc, needle in src, "rmc-page-fold-standards")

    experience = _read("templates/studio_os/modes/experience.html")
    add(
        "studio_experience_fold_stages",
        "Studio Experience uses data-rmc-fold-stages (Builder/Rollout/Templates)",
        'data-rmc-fold-stages' in experience
        and 'data-rmc-fold-stage="builder"' in experience
        and 'data-rmc-fold-stage="rollout"' in experience
        and 'data-rmc-fold-stage="templates"' in experience,
        "studio_os/modes/experience.html",
    )
    add(
        "studio_experience_fold_nav",
        "Studio Experience marks data-rmc-page-fold-nav=required",
        'data-rmc-page-fold-nav="required"' in experience,
        "studio_os/modes/experience.html",
    )

    cockpit = _read("templates/siteconfig/super/cockpit_configure.html")
    add(
        "cockpit_configure_fieldset_accordion",
        "Cockpit configure uses fieldset accordion compression",
        'data-rmc-fieldset-accordion="1"' in cockpit
        and 'data-rmc-page-fold-nav="required"' in cockpit,
        "siteconfig/super/cockpit_configure.html",
    )

    theme_personality = _read("templates/siteconfig/super/theme_personality_configure.html")
    add(
        "theme_personality_fieldset_accordion",
        "Theme personality configure uses fieldset accordion compression",
        'data-rmc-fieldset-accordion="1"' in theme_personality
        and 'data-rmc-page-fold-nav="required"' in theme_personality,
        "siteconfig/super/theme_personality_configure.html",
    )

    marketing_voice = _read("templates/siteconfig/super/marketing_voice_configure.html")
    add(
        "marketing_voice_fieldset_accordion",
        "Marketing voice configure uses fieldset accordion compression",
        'data-rmc-fieldset-accordion="1"' in marketing_voice
        and 'data-rmc-page-fold-nav="required"' in marketing_voice,
        "siteconfig/super/marketing_voice_configure.html",
    )

    catalog = _read("templates/marketplace/tenant_app_catalog.html")
    add(
        "tenant_app_catalog_fold_nav",
        "Tenant app catalog marks page-fold nav + section nav",
        'data-rmc-page-fold-nav="required"' in catalog
        and 'data-rmc-section-nav="auto"' in catalog,
        "marketplace/tenant_app_catalog.html",
    )

    intake_new = _read("templates/migration_cloud/intake_new.html")
    add(
        "migration_intake_new_fold_nav",
        "Migration intake marks page-fold nav",
        'data-rmc-page-fold-nav="required"' in intake_new,
        "migration_cloud/intake_new.html",
    )

    support_ticket = _read("templates/schools/super_support_ticket_detail.html")
    add(
        "support_ticket_detail_fold_nav",
        "Support ticket detail marks page-fold nav",
        'data-rmc-page-fold-nav="required"' in support_ticket,
        "schools/super_support_ticket_detail.html",
    )

    intake_start = _read("templates/migration_cloud/customer/intake_start.html")
    add(
        "migration_intake_start_fieldset_accordion",
        "Customer migration intake uses fieldset accordion",
        'data-rmc-fieldset-accordion="1"' in intake_start
        and 'data-rmc-page-fold-nav="required"' in intake_start,
        "migration_cloud/customer/intake_start.html",
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
