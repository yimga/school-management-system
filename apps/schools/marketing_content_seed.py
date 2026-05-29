"""
Marketing site seed helpers: sync config/marketing_content JSON from page definitions.

Used by ``seed_marketing_site`` and ``verify_marketing_site_seeded``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.schools.marketing_page_definitions import MARKETING_PAGE_DEFINITIONS

OS_PLATFORM_SLUGS: frozenset[str] = frozenset(
    {
        "platform-education-os",
        "platform-control-plane",
        "platform-marketplace",
        "platform-migration-cloud",
        "platform-runtime",
        "platform-integrations",
    }
)

PLATFORM_DIAGRAM = "images/marketing/platform-diagram-marketing.svg"
REQUIRED_JSON_KEYS: tuple[str, ...] = ("label", "seo_title", "headline")


def marketing_content_dir() -> Path:
    return Path(settings.BASE_DIR) / "config" / "marketing_content"


def platform_os_extras() -> dict[str, Any]:
    return {
        "diagram_path": PLATFORM_DIAGRAM,
        "data_viz_path": PLATFORM_DIAGRAM,
        "premium_platform_layout": True,
        "problem_section": {
            "title": "Built for institutional operators",
            "body": (
                "RunMyCampus ships one platform core with regional defaults, "
                "governed extensions, and audit-friendly operations."
            ),
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
                "bullets": [
                    "Clear ownership per workflow",
                    "Evidence for board reporting",
                ],
            },
            {
                "role": "Operations teams",
                "bullets": [
                    "Fewer shadow spreadsheets",
                    "Repeatable rollout playbooks",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Platform hub", "path": "/platform/"},
            {"label": "Book a demo", "path": "/demo/"},
        ],
    }


def page_definition_to_json_payload(slug: str, page: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "label": page.get("label", ""),
        "seo_title": page.get("seo_title", ""),
        "seo_description": page.get("seo_description", ""),
        "headline": page.get("headline", ""),
        "subheadline": page.get("subheadline", ""),
        "schema_type": page.get("schema_type", "WebPage"),
    }
    segments = page.get("segments")
    if isinstance(segments, list):
        payload["segments"] = segments
    if slug in OS_PLATFORM_SLUGS:
        payload["extras"] = platform_os_extras()
    return payload


def sync_marketing_content_json_files(*, force: bool = False) -> tuple[int, int]:
    """
    Write ``config/marketing_content/{slug}.json`` from MARKETING_PAGE_DEFINITIONS.

    Returns ``(written_count, skipped_existing_count)``.
    """
    mdir = marketing_content_dir()
    mdir.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    for slug, page in sorted(MARKETING_PAGE_DEFINITIONS.items()):
        dest = mdir / f"{slug}.json"
        if dest.is_file() and not force:
            skipped += 1
            continue
        payload = page_definition_to_json_payload(slug, page)
        dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        written += 1
    return written, skipped


def validate_marketing_content_json_files() -> list[str]:
    """Validate every page definition has a JSON file with required keys."""
    errors: list[str] = []
    mdir = marketing_content_dir()
    if not mdir.is_dir():
        return [f"missing marketing_content directory: {mdir}"]

    for slug in sorted(MARKETING_PAGE_DEFINITIONS):
        path = mdir / f"{slug}.json"
        if not path.is_file():
            errors.append(f"missing JSON for slug: {slug}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"{slug}.json unreadable: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{slug}.json root must be object")
            continue
        for key in REQUIRED_JSON_KEYS:
            if not str(data.get(key, "") or "").strip():
                errors.append(f"{slug}.json missing non-empty '{key}'")
    return errors


def validate_marketing_cms_db() -> list[str]:
    """Validate BlogPost + MarketingContent rows from seed_marketing_cms."""
    from apps.siteconfig.management.commands.seed_marketing_cms import (
        BLOG_SEED,
        MARKETING_CONTENT_SEED,
    )
    from apps.siteconfig.models_marketing import BlogPost, MarketingContent

    errors: list[str] = []
    for post in BLOG_SEED:
        slug = post["slug"]
        if not BlogPost.objects.filter(slug=slug, is_published=True).exists():
            errors.append(f"BlogPost not published: {slug}")

    for row in MARKETING_CONTENT_SEED:
        key = row["key"]
        locale = row.get("locale") or ""
        if not MarketingContent.objects.filter(key=key, locale=locale).exists():
            errors.append(f"MarketingContent missing: {key!r} locale={locale!r}")
    return errors


# Anchor msgids from scripts/seed_french_marketing_translations.py (subset gate).
FRENCH_MARKETING_MSGID_ANCHORS: tuple[str, ...] = (
    "Book a demo",
    "Pricing",
    "Login",
    "Book demo",
    "Why switch",
    "Platform overview",
    "See it live",
)


def _parse_po_msgstr_by_msgid(po_text: str) -> dict[str, str]:
    """Return msgid -> msgstr for a django.po file (single-line msgstr only)."""
    by_msgid: dict[str, str] = {}
    current_msgid: str | None = None
    for line in po_text.splitlines():
        if line.startswith("msgid "):
            current_msgid = line[6:].strip().strip('"')
            continue
        if line.startswith("msgstr ") and current_msgid is not None:
            by_msgid[current_msgid] = line[7:].strip().strip('"')
            current_msgid = None
    return by_msgid


def validate_french_marketing_translations() -> list[str]:
    """French locale must carry non-empty msgstr for anchor marketing chrome."""
    fr_po = Path(settings.BASE_DIR) / "locale" / "fr" / "LC_MESSAGES" / "django.po"
    if not fr_po.is_file():
        return [f"missing French catalog: {fr_po}"]
    try:
        by_msgid = _parse_po_msgstr_by_msgid(fr_po.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"French catalog unreadable: {exc}"]
    errors: list[str] = []
    for msgid in FRENCH_MARKETING_MSGID_ANCHORS:
        msgstr = (by_msgid.get(msgid) or "").strip()
        if not msgstr:
            errors.append(f"French marketing msgstr empty for: {msgid!r}")
    return errors


def validate_marketing_loop_assets() -> list[str]:
    """Committed regional loop binaries must pass ensure_marketing_loops gates."""
    import subprocess
    import sys

    repo = Path(settings.BASE_DIR)
    script = repo / "scripts" / "ensure_marketing_loops.py"
    if not script.is_file():
        return [f"missing ensure_marketing_loops.py: {script}"]
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-3:] if detail else ["ensure_marketing_loops failed"]
        return [f"marketing loop assets: {line}" for line in tail]
    return []
