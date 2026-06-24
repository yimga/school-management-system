#!/usr/bin/env python3
"""Gate: One Record Scroll wired on /storefront/ (§9 MARKETING_REDESIGN_DIRECTION)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []

    homepage = REPO / "templates/marketing/homepage.html"
    if not homepage.is_file():
        findings.append("missing templates/marketing/homepage.html")
    else:
        text = homepage.read_text(encoding="utf-8")
        for needle in (
            "_one_record_scroll.html",
            "mkt-one-record-scroll.js",
            "mkt-one-record-scroll.css",
        ):
            if needle not in text:
                findings.append(f"homepage.html: missing {needle}")

    partial = REPO / "templates/marketing/partials/sections/_one_record_scroll.html"
    if not partial.is_file():
        findings.append("missing _one_record_scroll.html partial")
    else:
        ptext = partial.read_text(encoding="utf-8")
        if "data-mkt-one-record-scroll" not in ptext:
            findings.append("_one_record_scroll.html: missing data-mkt-one-record-scroll")
        chapter_count = ptext.count("data-mkt-or-panel=")
        if chapter_count != 6:
            findings.append(f"_one_record_scroll.html: expected 6 chapters, found {chapter_count}")

    js = REPO / "static/marketing/js/mkt-one-record-scroll.js"
    if not js.is_file():
        findings.append("missing mkt-one-record-scroll.js")
    elif "pickByMidpoint" not in js.read_text(encoding="utf-8"):
        findings.append("mkt-one-record-scroll.js: missing pickByMidpoint scroll spy")

    urls = (REPO / "config/urls.py").read_text(encoding="utf-8")
    if "marketing_intent_homepage" not in urls or 'path("storefront/"' not in urls:
        findings.append("config/urls.py: missing storefront → marketing_intent_homepage")

    views = (REPO / "apps/schools/marketing_views.py").read_text(encoding="utf-8")
    chunk = views.split("def marketing_intent_homepage", 1)[-1].split("\ndef ", 1)[0]
    if "marketing/homepage.html" not in chunk:
        findings.append("marketing_intent_homepage: must render marketing/homepage.html")

    manifest = REPO / "scripts/marketing_css_bundle_manifest.json"
    if manifest.is_file() and "mkt-one-record-scroll.css" not in manifest.read_text(
        encoding="utf-8"
    ):
        findings.append("marketing_css_bundle_manifest.json: missing mkt-one-record-scroll.css")

    if findings:
        print("verify_marketing_one_record_scroll: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_marketing_one_record_scroll: ONE_RECORD_SCROLL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
