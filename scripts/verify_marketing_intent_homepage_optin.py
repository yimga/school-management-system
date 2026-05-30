#!/usr/bin/env python3
"""Gate: MARKETING_INTENT_HOMEPAGE opt-in wiring for apex / and /marketing/."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []

    settings = (REPO / "config/settings.py").read_text(encoding="utf-8")
    if "MARKETING_INTENT_HOMEPAGE" not in settings:
        findings.append("config/settings.py: missing MARKETING_INTENT_HOMEPAGE")

    views = (REPO / "apps/schools/marketing_views.py").read_text(encoding="utf-8")
    chunk = views.split("def marketing_landing", 1)[-1].split("\ndef ", 1)[0]
    if "MARKETING_INTENT_HOMEPAGE" not in chunk:
        findings.append("marketing_landing: missing MARKETING_INTENT_HOMEPAGE branch")
    if "marketing/homepage.html" not in chunk:
        findings.append("marketing_landing: missing marketing/homepage.html template branch")

    public_urls = (REPO / "config/public_urls.py").read_text(encoding="utf-8")
    if "def home(request):" not in public_urls or "marketing_landing(request)" not in public_urls:
        findings.append("public_urls.py: apex home must delegate to marketing_landing")

    homepage = REPO / "templates/marketing/homepage.html"
    storefront_route = REPO / "config/public_urls.py"
    if not homepage.is_file():
        findings.append("missing templates/marketing/homepage.html")
    elif "marketing_intent_homepage" not in storefront_route.read_text(encoding="utf-8"):
        findings.append("public_urls.py: missing marketing_intent_homepage route")

    if findings:
        print("verify_marketing_intent_homepage_optin: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "verify_marketing_intent_homepage_optin: "
        "MARKETING_INTENT_HOMEPAGE_OPTIN_PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
