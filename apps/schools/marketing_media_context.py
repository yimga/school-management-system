"""
Marketing media + geo context processor (VISUAL-ENGINE-10X).
"""
from __future__ import annotations

from apps.schools.marketing_geo_context import marketing_geo_context


def marketing_media_context(request):
    from apps.schools.marketing_local_context import marketing_local_context
    from apps.schools.marketing_stock_registry import (
        VERB_NAV_ITEMS,
        stock_media_for_page_slug,
    )

    out = {}
    out.update(marketing_geo_context(request))
    out.update(marketing_local_context(request))
    from apps.schools.marketing_media_matrix import PHONE_BAN_COUNTRIES

    cc = (out.get("geo") or {}).get("country_code", "")
    out["marketing_show_phone_ban_section"] = cc in PHONE_BAN_COUNTRIES
    slug = ""
    if hasattr(request, "resolver_match") and request.resolver_match:
        slug = str(request.resolver_match.kwargs.get("page_slug") or "")
    out["marketing_stock_media"] = stock_media_for_page_slug(slug)
    out["marketing_verb_nav"] = VERB_NAV_ITEMS
    return out
