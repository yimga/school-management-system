"""
GAP.12 / PATH_TO_100 IV.2–IV.3: Unified theme/layout token resolution.

Single entry point for portal, dashboard, and admin to read theme/experience tokens
so they share one design system. Resolvers here delegate to SiteSettings.get_theme_experience_settings()
which uses owned_payload(owner="brand_experience"); data ownership remains in brand_experience models.
"""

from __future__ import annotations

from typing import Any, Dict


def get_unified_theme_tokens(school: Any = None, request: Any = None) -> Dict[str, Any]:
    """
    Return theme/experience tokens for the given school (or request context).

    Use this from portal, dashboard, and admin views so all surfaces share the same
    token/layout contract. Ownership: brand_experience (ThemePack, BrandProfile, etc.).
    """
    try:
        from apps.platform_runtime.helpers import get_effective_site_settings

        site = get_effective_site_settings(request=request, school=school)
        if site is not None and callable(
            getattr(site, "get_theme_experience_settings", None)
        ):
            out = site.get_theme_experience_settings()
            return dict(out) if isinstance(out, dict) else {}
    except Exception:
        pass
    return {}
