"""
v3.6 — brand-asset manifest for marketplace connectors.

The v2.79 SVG sprite ships with 9 category-level glyphs (Bootstrap Icons MIT)
as a defensible default. Tenants who want real provider logos (Zoom blue
camera, Slack hashmark, etc.) drop slug-specific `<symbol id="integration-<slug>">`
into `static/sprites/integrations.svg`. This module catalogs:

  - the per-connector press-kit URL the operator visits to grab the SVG
  - the redistribution-license status as last reviewed
  - whether the slug-specific glyph is present in our sprite TODAY

`python manage.py check_brand_assets` reports the remaining gap so brand
work doesn't drift silently as new connectors register.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrandAssetEntry:
    """Per-connector brand-asset metadata."""
    slug: str
    press_kit_url: str
    license_status: str   # "permissive" | "review_required" | "restricted" | "unknown"
    license_note: str = ""


BRAND_ASSETS: list[BrandAssetEntry] = [
    BrandAssetEntry("zoom", "https://brand.zoom.us/",
                    "review_required",
                    "Zoom requires partner-program enrollment to use full logo; "
                    "their 'app marketplace' icon set is OK for hub display."),
    BrandAssetEntry("microsoft_teams", "https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general",
                    "review_required"),
    BrandAssetEntry("microsoft_teams_chat", "https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general",
                    "review_required"),
    BrandAssetEntry("google_meet", "https://about.google/brand-resource-center/logos-list/",
                    "review_required",
                    "Google logos OK for integrations UIs per their brand guide; "
                    "review per-product."),
    BrandAssetEntry("google_calendar", "https://about.google/brand-resource-center/logos-list/",
                    "review_required"),
    BrandAssetEntry("gmail", "https://about.google/brand-resource-center/logos-list/",
                    "review_required"),
    BrandAssetEntry("outlook_calendar", "https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general",
                    "review_required"),
    BrandAssetEntry("outlook_mail", "https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general",
                    "review_required"),
    BrandAssetEntry("webex", "https://www.webex.com/branding-guidelines.html",
                    "review_required"),
    BrandAssetEntry("slack", "https://slack.com/brand-guidelines",
                    "review_required",
                    "Slack has a 'Slack-built integrations' icon set OK to use; "
                    "main wordmark needs partner agreement."),
    BrandAssetEntry("discord", "https://discord.com/branding",
                    "review_required"),
    BrandAssetEntry("mailgun", "https://www.mailgun.com/brand/",
                    "review_required"),
    BrandAssetEntry("sendgrid", "https://sendgrid.com/brand/",
                    "review_required"),
    BrandAssetEntry("postmark", "https://postmarkapp.com/brand",
                    "review_required"),
    BrandAssetEntry("amazon_ses", "https://aws.amazon.com/architecture/icons/",
                    "permissive",
                    "AWS architecture icons are explicitly OK for product diagrams."),
    BrandAssetEntry("sparkpost", "https://www.sparkpost.com",
                    "unknown"),
    BrandAssetEntry("brevo", "https://www.brevo.com/about/brand/",
                    "review_required"),
    BrandAssetEntry("mandrill", "https://mailchimp.com/brand-assets/",
                    "review_required"),
    BrandAssetEntry("mailersend", "https://www.mailersend.com",
                    "unknown"),
    BrandAssetEntry("mailjet", "https://www.mailjet.com",
                    "unknown"),
    BrandAssetEntry("resend", "https://resend.com",
                    "unknown"),
    BrandAssetEntry("smtp_generic", "", "permissive",
                    "Generic SMTP — no provider logo applies."),
    BrandAssetEntry("whatsapp", "https://about.fb.com/brand/",
                    "restricted",
                    "Meta brand assets require explicit written permission."),
    BrandAssetEntry("push", "", "permissive",
                    "Generic push channel — no provider logo applies."),
    BrandAssetEntry("sms", "", "permissive",
                    "Generic SMS channel — no provider logo applies."),
    BrandAssetEntry("stripe", "https://stripe.com/newsroom/brand-assets",
                    "review_required",
                    "Stripe provides OK-to-use 'powered by Stripe' marks."),
    BrandAssetEntry("badges", "https://openbadges.org", "permissive",
                    "Open Badges spec marks are CC-licensed."),
    BrandAssetEntry("lms", "https://www.imsglobal.org/spec/lti/v1p3/",
                    "permissive",
                    "LTI is a standard — IMS Global mark may apply per their guidelines."),
]


def _read_sprite_text() -> str:
    """Read static/sprites/integrations.svg from the repo root.

    Path resolution mirrors how the runtime serves the sprite via {% static %}.
    Returns "" if the file is missing (test environments without static set up).
    """
    here = Path(__file__).resolve().parent
    # apps/integrations_marketplace/ → ../../static/sprites/integrations.svg
    candidate = here.parent.parent / "static" / "sprites" / "integrations.svg"
    if not candidate.exists():
        return ""
    try:
        return candidate.read_text(encoding="utf-8")
    except OSError:
        return ""


_SYMBOL_ID_RE = re.compile(r'<symbol\s+id\s*=\s*"([^"]+)"', re.IGNORECASE)


def sprite_symbol_ids() -> set[str]:
    """Set of `<symbol id="...">` values currently in the integrations sprite."""
    text = _read_sprite_text()
    if not text:
        return set()
    return set(_SYMBOL_ID_RE.findall(text))


def report() -> dict:
    """Audit the connector registry against the sprite.

    Returns a structured report:
      {
        "total_connectors": N,
        "with_slug_glyph": [slug, ...],         # has integration-<slug> symbol
        "category_fallback_only": [slug, ...],  # only category glyph; sprite swap opportunity
        "license_status_counts": {status: count},
      }
    """
    from apps.integrations_marketplace.connector_registry import list_connectors

    symbol_ids = sprite_symbol_ids()
    with_slug: list[str] = []
    category_only: list[str] = []
    for c in list_connectors():
        slug_symbol = f"integration-{c.slug}"
        if slug_symbol in symbol_ids:
            with_slug.append(c.slug)
        else:
            category_only.append(c.slug)
    license_counts: dict[str, int] = {}
    for entry in BRAND_ASSETS:
        license_counts[entry.license_status] = (
            license_counts.get(entry.license_status, 0) + 1
        )
    return {
        "total_connectors": len(with_slug) + len(category_only),
        "with_slug_glyph": sorted(with_slug),
        "category_fallback_only": sorted(category_only),
        "license_status_counts": license_counts,
    }


__all__ = [
    "BRAND_ASSETS",
    "BrandAssetEntry",
    "report",
    "sprite_symbol_ids",
]
