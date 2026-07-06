"""Global payment command center — country/rail/readiness rollup (SFDP 1473)."""

from __future__ import annotations

from django.conf import settings
from apps.accounts.decorators import require_permission
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import render

from apps.finance.payment_evidence_generator import evidence_paths_for_country
from apps.finance.payment_lane2_status import build_lane2_corridor_rows
from apps.finance.regional_payment_profiles import (
    get_normalized_regional_profile,
    list_supported_country_codes,
)


@require_permission("finance.view", "finance.manage")
def global_payment_command_center(request: HttpRequest):
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("Open from a school (tenant) workspace.")

    q = (request.GET.get("q") or "").strip().upper()
    risk = (request.GET.get("risk") or "").strip().lower()

    rows: list[dict] = []
    for iso2 in list_supported_country_codes():
        profile = get_normalized_regional_profile(iso2) or {}
        if q and q not in iso2 and q not in str(profile.get("label") or "").upper():
            continue
        tier = str(profile.get("risk_tier") or "")
        if risk and tier != risk:
            continue
        rows.append(
            {
                "country_code": iso2,
                "label": profile.get("label"),
                "currency": profile.get("currency"),
                "currency_display": profile.get("currency_display"),
                "primary_rail": profile.get("primary_rail"),
                "risk_tier": tier,
                "small_market_fallback": profile.get("small_market_fallback"),
                "canonical_rail_classes": profile.get("canonical_rail_classes") or [],
                "evidence_paths": evidence_paths_for_country(iso2),
            }
        )

    return render(
        request,
        "finance/global_payment_command_center.html",
        {
            "school": school,
            "country_rows": rows[:500],
            "total_countries": len(list_supported_country_codes()),
            "filtered_count": len(rows),
            "lane2_corridors": build_lane2_corridor_rows(school=school),
            "filter_q": q,
            "filter_risk": risk,
        },
    )
