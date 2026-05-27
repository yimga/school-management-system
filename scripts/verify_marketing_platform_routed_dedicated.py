#!/usr/bin/env python3
"""Every routed platform-* slug must resolve to a dedicated template (not generic)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PUBLIC_URLS = REPO / "config" / "public_urls.py"
GENERIC = "marketing/pages/type_platform_generic.html"
HUB = "marketing/pages/type_platform_hub.html"


def _routed_platform_slugs() -> set[str]:
    text = PUBLIC_URLS.read_text(encoding="utf-8")
    return {m.group(1).lower() for m in re.finditer(r'"page_slug":\s*"(platform-[^"]+)"', text)}


def main() -> int:
    sys.path.insert(0, str(REPO))
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.schools.marketing_views import (  # noqa: WPS433
        _MARKETING_PLATFORM_DIFFERENTIATED_TEMPLATES,
        _marketing_page_type_template,
    )

    errors: list[str] = []
    slugs = _routed_platform_slugs()
    if not slugs:
        errors.append("no platform page_slug entries found in public_urls.py")

    for slug in sorted(slugs):
        tpl = _marketing_page_type_template(slug)
        if tpl == GENERIC:
            errors.append(f"{slug} resolves to generic template")
        elif tpl is None:
            errors.append(f"{slug} has no type template (falls back to marketing_page.html)")
        elif slug not in _MARKETING_PLATFORM_DIFFERENTIATED_TEMPLATES:
            errors.append(f"{slug} template {tpl} not registered in differentiated map")

    hub_tpl = _marketing_page_type_template("platform")
    if hub_tpl != HUB:
        errors.append(f"platform hub expected {HUB}, got {hub_tpl}")

    for slug, rel in _MARKETING_PLATFORM_DIFFERENTIATED_TEMPLATES.items():
        full = REPO / "templates" / rel
        if not full.is_file():
            errors.append(f"missing template file for {slug}: {rel}")

    if errors:
        print("verify_marketing_platform_routed_dedicated: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"verify_marketing_platform_routed_dedicated: OK ({len(slugs)} routed slugs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
