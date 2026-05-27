"""
Marketing media + geo context processor (VISUAL-ENGINE-10X).
"""
from __future__ import annotations

from apps.schools.marketing_geo_context import marketing_geo_context


def marketing_media_context(request):
    from apps.schools.marketing_local_context import marketing_local_context

    out = {}
    out.update(marketing_geo_context(request))
    out.update(marketing_local_context(request))
    from apps.schools.marketing_media_matrix import PHONE_BAN_COUNTRIES

    cc = (out.get("geo") or {}).get("country_code", "")
    out["marketing_show_phone_ban_section"] = cc in PHONE_BAN_COUNTRIES
    return out
