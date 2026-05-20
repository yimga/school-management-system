#!/usr/bin/env python3
"""Gate: marketing shell ships SEO primitives (meta, OG partial, JSON-LD, hero h1)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

BASE = REPO / "templates" / "marketing" / "base_marketing.html"
LANDING = REPO / "templates" / "schools" / "marketing_landing_v2.html"
PRICING = REPO / "templates" / "marketing" / "pages" / "type_pricing.html"
STRUCTURED = REPO / "templates" / "marketing" / "partials" / "mkt_structured_data.html"
SOCIAL = REPO / "templates" / "partials" / "rmc_social_meta.html"
ROTATING_H1 = REPO / "templates" / "marketing" / "components" / "_rotating_headline.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    errors: list[str] = []

    for path in (BASE, LANDING, PRICING, STRUCTURED, SOCIAL, ROTATING_H1):
        if not path.is_file():
            errors.append(f"missing: {path.relative_to(REPO)}")

    base = _read(BASE)
    if "mkt_structured_data.html" not in base:
        errors.append("base_marketing.html must include mkt_structured_data.html")
    if "rmc_social_meta.html" not in base:
        errors.append("base_marketing.html must include rmc_social_meta.html")
    if "canonical_url" not in base and 'rel="canonical"' not in base:
        errors.append("base_marketing.html missing canonical link support")
    if 'name="viewport"' not in base:
        errors.append("base_marketing.html missing viewport meta")

    social = _read(SOCIAL)
    for token in ("og:title", "og:description", "twitter:card"):
        if token not in social:
            errors.append(f"rmc_social_meta.html missing {token}")

    structured = _read(STRUCTURED)
    if "application/ld+json" not in structured:
        errors.append("mkt_structured_data.html missing JSON-LD script type")

    landing = _read(LANDING)
    if "_rotating_headline.html" not in landing:
        errors.append("marketing_landing_v2.html must include _rotating_headline.html (h1)")

    h1 = _read(ROTATING_H1)
    if not re.search(r"<h1\b", h1, re.I):
        errors.append("_rotating_headline.html must emit a single hero <h1>")

    pricing = _read(PRICING)
    hero_partial = REPO / "templates" / "marketing" / "components" / "_personality_hero.html"
    pricing_has_h1 = bool(re.search(r"<h1\b", pricing, re.I))
    if not pricing_has_h1 and "_personality_hero.html" in pricing and hero_partial.is_file():
        pricing_has_h1 = bool(re.search(r"<h1\b", _read(hero_partial), re.I))
    if not pricing_has_h1:
        errors.append("type_pricing.html must emit <h1> (direct or via _personality_hero.html)")

    if errors:
        for e in errors:
            print(f"verify_marketing_seo_shell: {e}", file=sys.stderr)
        return 1

    print("verify_marketing_seo_shell: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
