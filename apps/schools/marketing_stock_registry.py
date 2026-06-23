"""
Curated stock + cinematic media registry for Threshold Era marketing.

URLs resolve through env overrides first (7-layer cascade), then defaults.
Defaults use Unsplash (free license) — replace via env for production CDN/AI assets.
"""
from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.templatetags.static import static

# slug → asset bundle for inner pages and ascension chapters
STOCK_MEDIA_REGISTRY: dict[str, dict[str, Any]] = {
    "home": {
        "hero_photo_env": "MARKETING_STOCK_HERO_CAMPUS_URL",
        "hero_photo_default": "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?auto=format&fit=crop&w=1920&q=80",
        "hero_video_env": "MARKETING_HERO_VIDEO_URL",
        "poster_env": "MARKETING_HERO_VIDEO_POSTER_URL",
        "poster_default": "marketing/img/posters/sovereign_default.svg",
        "credit": "Photo: Unsplash · campus at dawn (illustrative)",
        "alt": "Modern campus at sunrise — illustrative acquisition hero",
    },
    "platform-admissions": {
        "hero_photo_env": "MARKETING_STOCK_ADMISSIONS_URL",
        "hero_photo_default": "https://images.unsplash.com/photo-1503676260728-1c00da094a0b?auto=format&fit=crop&w=1600&q=80",
        "credit": "Photo: Unsplash · enrollment (illustrative)",
        "alt": "Students and families at school enrollment — illustrative",
        "viz": "admissions_flow",
    },
    "platform-fees-payments": {
        "hero_photo_env": "MARKETING_STOCK_FINANCE_URL",
        "hero_photo_default": "https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&w=1600&q=80",
        "credit": "Photo: Unsplash · finance (illustrative)",
        "alt": "School finance and payments — illustrative ledger context",
        "viz": "split_ledger",
    },
    "platform-grading-report-cards": {
        "hero_photo_env": "MARKETING_STOCK_CLASSROOM_URL",
        "hero_photo_default": "marketing/img/ascension/classroom-cinematic.png",
        "hero_static": True,
        "credit": "RunMyCampus · AI editorial composite (illustrative)",
        "alt": "Collaborative classroom learning — illustrative",
        "viz": "gradebook_viz",
    },
    "platform-offline-first": {
        "hero_photo_env": "MARKETING_STOCK_RUGGED_URL",
        "hero_photo_default": "https://images.unsplash.com/photo-1580582932707-520aedcedb7d?auto=format&fit=crop&w=1600&q=80",
        "credit": "Photo: Unsplash · rural school (illustrative)",
        "alt": "School operating with limited connectivity — illustrative",
        "viz": "transit_viz",
    },
    "platform-parent-portal": {
        "hero_photo_env": "MARKETING_STOCK_PARENT_URL",
        "hero_photo_default": "https://images.unsplash.com/photo-1516627145497-ae6968895b74?auto=format&fit=crop&w=1600&q=80",
        "credit": "Photo: Unsplash · parent and child (illustrative)",
        "alt": "Parent checking school updates on phone — illustrative",
    },
    "platform-analytics": {
        "hero_photo_env": "MARKETING_STOCK_LEADERSHIP_URL",
        "hero_photo_default": "https://images.unsplash.com/photo-1552664730-d307ca884978?auto=format&fit=crop&w=1600&q=80",
        "credit": "Photo: Unsplash · leadership (illustrative)",
        "alt": "School leadership reviewing outcomes — illustrative",
        "viz": "enterprise_constellation_viz",
    },
    "ascension-gate": {
        "hero_photo_env": "MARKETING_STOCK_ASCENSION_GATE_URL",
        "hero_photo_default": "marketing/img/ascension/gate-aurora-campus.svg",
        "hero_static": True,
        "credit": "RunMyCampus · generative editorial composite (illustrative)",
        "alt": "Aurora over a global campus — education OS hero",
    },
    "ascension-parent": {
        "hero_photo_env": "MARKETING_STOCK_ASCENSION_PARENT_URL",
        "hero_photo_default": "marketing/img/ascension/parent-window-cinematic.png",
        "hero_static": True,
        "credit": "RunMyCampus · AI editorial composite (illustrative)",
        "alt": "Parent receiving calm school update — illustrative",
    },
}

VERB_NAV_ITEMS: tuple[dict[str, str], ...] = (
    {"key": "run", "label": "Run", "icon": "bi-lightning-charge", "url_name": "marketing_platform"},
    {"key": "teach", "label": "Teach", "icon": "bi-mortarboard", "url_name": "marketing_platform_teacher_portal"},
    {"key": "pay", "label": "Pay", "icon": "bi-wallet2", "url_name": "marketing_platform_fees_payments"},
    {"key": "talk", "label": "Talk", "icon": "bi-chat-heart", "url_name": "marketing_platform_communications"},
    {"key": "govern", "label": "Govern", "icon": "bi-shield-check", "url_name": "marketing_trust_center"},
    {"key": "grow", "label": "Grow", "icon": "bi-graph-up-arrow", "url_name": "marketing_grow_hub"},
)


def _env_url(key: str) -> str:
    return (os.environ.get(key) or getattr(settings, key, None) or "").strip()


def resolve_stock_media(slug: str) -> dict[str, Any]:
    """Resolve photo/video/poster URLs for a page slug or ascension chapter key."""
    entry = STOCK_MEDIA_REGISTRY.get(slug) or STOCK_MEDIA_REGISTRY.get("home", {})
    photo_env = entry.get("hero_photo_env", "")
    photo = _env_url(photo_env) if photo_env else ""
    if not photo:
        default = entry.get("hero_photo_default", "")
        if entry.get("hero_static") and default and not default.startswith("http"):
            photo = static(default)
        else:
            photo = default

    video_env = entry.get("hero_video_env", "")
    video = _env_url(video_env) if video_env else ""
    if not video and slug == "home":
        video = _env_url("MARKETING_HERO_VIDEO_URL")

    poster_env = entry.get("poster_env", "")
    poster = _env_url(poster_env) if poster_env else ""
    if not poster:
        pd = entry.get("poster_default", "")
        poster = static(pd) if pd and not pd.startswith("http") else pd

    return {
        "slug": slug,
        "photo_url": photo,
        "video_url": video,
        "poster_url": poster,
        "credit": entry.get("credit", ""),
        "alt": entry.get("alt", ""),
        "viz_key": entry.get("viz", ""),
    }


def stock_media_for_page_slug(page_slug: str) -> dict[str, Any]:
    slug = (page_slug or "home").strip().lower()
    if slug not in STOCK_MEDIA_REGISTRY:
        # Prefix match: platform-fees-payments → registry key
        for key in STOCK_MEDIA_REGISTRY:
            if slug.startswith(key) or key in slug:
                return resolve_stock_media(key)
    return resolve_stock_media(slug if slug in STOCK_MEDIA_REGISTRY else "home")
