"""
Country Readiness operator surface.

Renders the world-wide launch-readiness truth table from
`apps.finance.country_readiness_register` — one row per ISO country showing
exactly what a tenant must configure (just add an API key) versus what the
platform must finish first (promote a payment adapter to live, ship a locale).

Pairs with the Lane-2 readiness scoreboard: lane2 shows PSP adapter status in
the abstract; this projects that status onto all 250 countries so the operator
can answer "are we launch-ready in <country>?" and "which single adapter, if
promoted to live, unblocks the most of the world?"

Read-only, staff-gated, no DB writes — pure projection over the SOT registers.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def manager_country_readiness(request):
    from apps.schools.control_plane import user_has_control_plane_access
    from django.http import HttpResponseForbidden

    if not user_has_control_plane_access(getattr(request, "user", None)):
        return HttpResponseForbidden("Operator access required.")

    from apps.finance.country_readiness_register import all_assessments, summary

    s = summary()
    tier_cards = [
        {
            "tier": t,
            "count": s["by_tier"].get(t, 0),
            "label": s["tier_labels"][t],
            "tone": s["tier_tone"][t],
        }
        for t in s["tier_order"]
    ]
    rows = list(all_assessments().values())

    active_tier = (request.GET.get("tier") or "").strip()
    query = (request.GET.get("q") or "").strip()
    data_state = (request.GET.get("data_state") or "").strip()
    if active_tier:
        rows = [r for r in rows if r["overall_tier"] == active_tier]
    if data_state in ("defined", "placeholder"):
        rows = [r for r in rows if r["data_state"] == data_state]
    if query:
        q = query.lower()
        rows = [
            r for r in rows
            if q in r["label"].lower() or q in r["country_code"].lower() or q in r["currency"].lower()
        ]

    # Machine-readable projection — closes the "tenants just need the data" loop. A tenant (or their
    # integrator) can GET ?format=json and read exactly what their country needs to go live.
    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse(
            {
                "generated_for": "country-readiness",
                "summary": {
                    k: s[k] for k in (
                        "total_countries", "defined_corridors", "placeholder_corridors",
                        "by_tier", "by_data_state", "by_blocking_psp", "by_locale",
                        "by_risk_tier", "live_rail_count",
                    )
                },
                "row_count": len(rows),
                "countries": rows,
            },
            json_dumps_params={"ensure_ascii": False},
        )

    return render(
        request,
        "finance/country_readiness.html",
        {
            "summary": s,
            "tier_cards": tier_cards,
            "rows": rows,
            "row_count": len(rows),
            "active_tier": active_tier,
            "active_data_state": data_state,
            "query": query,
        },
    )
