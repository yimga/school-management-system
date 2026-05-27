#!/usr/bin/env python3
"""Seed config/marketing_content/*.json for OS-tier platform slugs (from page definitions)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTENT = REPO / "config" / "marketing_content"
DIAGRAM = "images/marketing/platform-diagram-marketing.svg"

OS_SLUGS = (
    "platform-education-os",
    "platform-control-plane",
    "platform-marketplace",
    "platform-migration-cloud",
    "platform-runtime",
    "platform-integrations",
)


def _extras(slug: str) -> dict:
    return {
        "diagram_path": DIAGRAM,
        "data_viz_path": DIAGRAM,
        "premium_platform_layout": True,
        "problem_section": {
            "title": "Built for institutional operators",
            "body": "RunMyCampus ships one platform core with regional defaults, governed extensions, and audit-friendly operations.",
        },
        "workflow_steps": [
            "Discover capability",
            "Configure tenant",
            "Pilot with one campus",
            "Expand network-wide",
            "Measure outcomes",
        ],
        "benefits_by_role": [
            {
                "role": "School leadership",
                "bullets": ["Clear ownership per workflow", "Evidence for board reporting"],
            },
            {
                "role": "Operations teams",
                "bullets": ["Fewer shadow spreadsheets", "Repeatable rollout playbooks"],
            },
        ],
        "related_platform_links": [
            {"label": "Platform hub", "path": "/platform/"},
            {"label": "Book a demo", "path": "/demo/"},
        ],
    }


def main() -> int:
    sys.path.insert(0, str(REPO))
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.schools.marketing_page_definitions import MARKETING_PAGE_DEFINITIONS

    written = 0
    for slug in OS_SLUGS:
        dest = CONTENT / f"{slug}.json"
        if dest.is_file():
            continue
        page = MARKETING_PAGE_DEFINITIONS.get(slug)
        if not page:
            print(f"seed_marketing_platform_os_content: missing definition {slug}", file=sys.stderr)
            return 1
        payload = {**page, "extras": _extras(slug)}
        dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        written += 1
        print(f"  wrote {dest.name}")
    print(f"seed_marketing_platform_os_content: OK ({written} new files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
