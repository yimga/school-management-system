#!/usr/bin/env python3
"""Gate: marketing personality sections use 100dvh viewport-lock + geo shell attrs."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SECTIONS = REPO / "templates/marketing/partials/sections"
BASE = REPO / "templates/marketing/base_marketing.html"


def main() -> int:
    findings: list[str] = []
    for name in ("_sovereign_kernel.html", "_clinical_ledger.html", "_rugged_engine.html"):
        path = SECTIONS / name
        if not path.is_file():
            findings.append(f"missing {path.relative_to(REPO)}")
            continue
        text = path.read_text(encoding="utf-8")
        if "mkt-ve-section--viewport-lock" not in text:
            findings.append(f"{name}: missing viewport-lock class")
        if 'data-mkt-scroll-policy="viewport-lock"' not in text:
            findings.append(f"{name}: missing viewport-lock scroll policy")

    homepage = REPO / "templates/marketing/homepage.html"
    if homepage.is_file():
        hp = homepage.read_text(encoding="utf-8")
        for partial in (
            "_sovereign_kernel.html",
            "_clinical_ledger.html",
            "_rugged_engine.html",
        ):
            if partial not in hp:
                findings.append(f"homepage.html missing include {partial}")
    else:
        findings.append("missing templates/marketing/homepage.html")

    if BASE.is_file():
        base = BASE.read_text(encoding="utf-8")
        if "geo.locale" not in base or "geo.direction" not in base:
            findings.append("base_marketing.html: missing geo.locale/geo.direction on <html>")
    else:
        findings.append("missing base_marketing.html")

    settings_py = REPO / "config/settings.py"
    if "RunMyCampusGeoMiddleware" not in settings_py.read_text(encoding="utf-8"):
        findings.append("settings.py missing RunMyCampusGeoMiddleware")

    css = REPO / "static/marketing/css/marketing-visual-engine.css"
    if css.is_file():
        css_text = css.read_text(encoding="utf-8")
        if "max-height: 100dvh" not in css_text:
            findings.append("marketing-visual-engine.css: missing max-height 100dvh")
        if ".mkt-edos-text-shield" not in css_text:
            findings.append("marketing-visual-engine.css: missing text-shield")
    else:
        findings.append("missing marketing-visual-engine.css")

    if findings:
        print("verify_marketing_intent_viewport: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_marketing_intent_viewport: MARKETING_INTENT_VIEWPORT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
