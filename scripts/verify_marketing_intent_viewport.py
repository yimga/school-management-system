#!/usr/bin/env python3
"""Gate: /storefront/ One Record Scroll + personality page shells + geo middleware."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASE = REPO / "templates/marketing/base_marketing.html"
STAGE_DIR = REPO / "templates/marketing/partials/one_record_scroll"

PERSONALITY_PAGES = (
    "zero_ui_lab.html",
    "enterprise_ledger.html",
    "academics.html",
    "edge_mesh.html",
    "compliance.html",
    "pricing.html",
)

STOREFRONT_HOMEPAGE_MARKERS = (
    "_one_record_scroll.html",
    "mkt-one-record-scroll.js",
    "mkt-one-record-scroll.css",
)

SCROLL_PARTIAL_MARKERS = (
    "data-mkt-one-record-scroll",
)

STAGE_SIM_HOOKS = (
    ("_stage_speed_duel.html", "data-mkt-speed-duel"),
    ("_stage_sovereign_wizard.html", "data-mkt-sandbox-wizard"),
    ("_stage_fluid_gradebook.html", "data-mkt-gradebook-morph"),
    ("_stage_clinical_ledger.html", "data-mkt-split-ledger"),
    ("_stage_rugged_console.html", "data-mkt-network-state"),
)


def main() -> int:
    findings: list[str] = []

    homepage = REPO / "templates/marketing/homepage.html"
    if not homepage.is_file():
        findings.append("missing templates/marketing/homepage.html")
    else:
        hp = homepage.read_text(encoding="utf-8")
        for marker in STOREFRONT_HOMEPAGE_MARKERS:
            if marker not in hp:
                findings.append(f"homepage.html missing {marker}")
        if "mkt-speed-duel.js" not in hp:
            findings.append("homepage.html missing mkt-speed-duel.js (stage sim)")

    scroll_partial = REPO / "templates/marketing/partials/sections/_one_record_scroll.html"
    if not scroll_partial.is_file():
        findings.append("missing _one_record_scroll.html partial")
    else:
        sp = scroll_partial.read_text(encoding="utf-8")
        for marker in SCROLL_PARTIAL_MARKERS:
            if marker not in sp:
                findings.append(f"_one_record_scroll.html missing {marker}")
        if sp.count("data-mkt-or-panel=") != 6:
            findings.append("_one_record_scroll.html: expected 6 chapter panels")

    for stage_file, hook in STAGE_SIM_HOOKS:
        path = STAGE_DIR / stage_file
        if not path.is_file():
            findings.append(f"missing stage partial {stage_file}")
            continue
        if hook not in path.read_text(encoding="utf-8"):
            findings.append(f"{stage_file}: missing sim hook {hook}")

    for page in PERSONALITY_PAGES:
        path = REPO / "templates/marketing" / page
        if not path.is_file():
            findings.append(f"missing personality page {page}")
            continue
        text = path.read_text(encoding="utf-8")
        if "data-mkt-personality-page=" not in text:
            findings.append(f"{page}: missing data-mkt-personality-page")
        if "mkt-personality-page__viewport" not in text:
            findings.append(f"{page}: missing mkt-personality-page__viewport shell")

    if BASE.is_file():
        base = BASE.read_text(encoding="utf-8")
        if "geo.locale" not in base or "geo.direction" not in base:
            findings.append("base_marketing.html: missing geo.locale/geo.direction on <html>")
    else:
        findings.append("missing base_marketing.html")

    settings_py = REPO / "config/settings.py"
    if "RunMyCampusGeoMiddleware" not in settings_py.read_text(encoding="utf-8"):
        findings.append("settings.py missing RunMyCampusGeoMiddleware")

    or_css = REPO / "static/marketing/css/mkt-one-record-scroll.css"
    if not or_css.is_file():
        findings.append("missing mkt-one-record-scroll.css")
    else:
        css_text = or_css.read_text(encoding="utf-8")
        if ".mkt-or__stage-wrap" not in css_text:
            findings.append("mkt-one-record-scroll.css: missing sticky stage wrap")

    if findings:
        print("verify_marketing_intent_viewport: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_marketing_intent_viewport: MARKETING_INTENT_VIEWPORT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
