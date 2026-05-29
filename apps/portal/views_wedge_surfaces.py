"""v4.00.36 — Grouped surfaces that consume ``?wedge=<id>`` for filtering.

Three concrete demonstrations of the canonical filter contract documented
on each wedge's detail page:

* ``/portal/super/wedges/countries/?wedge=<id>`` — country localization
  list filtered to the wedge's region. Tier-B region wedges map to a
  fixed country set; non-region wedges return the full list.
* ``/portal/super/wedges/integrations/?wedge=<id>`` — integrations
  marketplace catalog filtered to a wedge's capability/domain facets.
* ``/portal/super/wedges/grading-scales/?wedge=<id>`` — grading scales
  filtered to the wedge's delivery facet (mastery / cohort / competency).

All three render staff-only and ship a ``?format=json`` export.
"""
from __future__ import annotations

import logging
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.siteconfig._wedge_registry import wedge

logger = logging.getLogger(__name__)


# ----- Region mapping for Tier-B wedges -----------------------------------
#
# Built from the canonical ISO 3166-1 alpha-2 codes the platform seeds. A
# wedge id (Tier-B only) projects to a set of country codes; everything
# else returns ``None`` meaning "no filter applied".

_TIER_B_REGION: dict[int, set[str]] = {
    7: {  # Africa
        "NG", "GH", "KE", "ZA", "EG", "MA", "TN", "DZ", "TZ", "UG", "ET",
        "RW", "SN", "CI", "CM", "TG", "BJ", "BF", "ML", "NE", "LR", "GM",
        "SL", "ZW", "ZM", "MZ", "AO", "MG", "SO", "ER", "DJ", "SS", "MW",
        "BW", "NA", "LS", "SZ", "GW", "CV", "ST", "CG", "CD", "GN", "GA",
        "TD", "CF", "SD", "BI",
    },
    8: {  # Asia
        "PK", "BD", "LK", "NP", "PH", "ID", "MY", "VN", "TH",
        "IN", "JP", "KR", "CN", "TW", "SG", "HK", "MM", "KH", "LA",
    },
    9: {  # Europe (beyond UK)
        "DE", "FR", "ES", "IT", "PT", "NL", "BE", "LU", "AT", "CH",
        "SE", "NO", "DK", "FI", "IS", "PL", "CZ", "HU", "RO", "BG",
        "GR", "IE", "RU", "UA", "TR",
    },
    10: {  # North America
        "US", "CA", "MX",
    },
    11: {  # South America
        "BR", "AR", "CL", "CO", "PE", "UY", "EC", "BO", "VE", "PY", "GY", "SR",
    },
    12: {  # Oceania
        "AU", "NZ", "FJ", "PG", "WS", "TO",
    },
    13: {  # MENA
        "EG", "MA", "TN", "DZ", "LY", "AE", "SA", "QA", "KW", "BH", "OM",
        "LB", "JO", "SY", "IQ", "PS", "YE",
    },
}


# ----- Integration facet map for Tier-A/F integration wedges ---------------
#
# Maps wedge id → a (capability, domain) facet pair. The integrations list
# is then filtered by the listing's facet matching.

_INTEGRATION_FACETS: dict[int, dict[str, str]] = {
    2: {"capability": "integration", "domain": "lms"},
    44: {"capability": "integration", "domain": "identity"},
    45: {"capability": "integration", "domain": "identity"},
}


# ----- Grading-scale facet map for Tier-D/E wedges -------------------------

_GRADING_DELIVERY: dict[int, str] = {
    26: "competency",
    27: "mastery",
    28: "project",
    29: "self-paced",
    30: "cohort",
    32: "tvet",
    38: "language",
}


# ----- helpers ------------------------------------------------------------


def _wants_json(request: HttpRequest) -> bool:
    fmt = (request.GET.get("format") or "").lower()
    return fmt == "json"


def _wedge_from_request(request: HttpRequest) -> dict[str, Any] | None:
    raw = (request.GET.get("wedge") or "").strip()
    if not raw:
        return None
    try:
        return wedge(int(raw))
    except (ValueError, TypeError):
        return wedge(raw)


# ----- 1) Country localization surface ------------------------------------


@staff_member_required
@require_http_methods(["GET"])
def countries_by_wedge(request):
    """Country localization list filtered by ``?wedge=<id>``."""
    try:
        from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    except Exception as exc:  # noqa: BLE001
        logger.warning("country localization unavailable: %s", exc)
        COUNTRY_LOCALIZATION = {}

    w = _wedge_from_request(request)
    allowed: set[str] | None = None
    if w is not None and w["id"] in _TIER_B_REGION:
        allowed = _TIER_B_REGION[w["id"]]

    rows: list[dict[str, Any]] = []
    for cc, info in COUNTRY_LOCALIZATION.items():
        if allowed is not None and cc not in allowed:
            continue
        rows.append({
            "country_code": cc,
            "calendar_label": (info.get("calendar_system") or {}).get("label", ""),
            "school_type_count": len(info.get("school_types") or []),
            "education_level_count": len(info.get("education_levels") or []),
            "languages": list(info.get("languages") or []),
        })
    rows.sort(key=lambda r: r["country_code"])

    if _wants_json(request):
        return JsonResponse({
            "success": True,
            "wedge": w["id"] if w else None,
            "count": len(rows),
            "rows": rows,
        })
    return render(request, "super/wedges/surface_countries.html", {
        "wedge": w,
        "rows": rows,
        "total": len(rows),
        "is_filtered": allowed is not None,
    })


# ----- 2) Integrations marketplace surface --------------------------------


@staff_member_required
@require_http_methods(["GET"])
def integrations_by_wedge(request):
    """Integrations catalog list filtered by ``?wedge=<id>``.

    Reads either the marketplace listing model when available, or falls
    back to a static catalog table so the page is never blank in dev.
    """
    w = _wedge_from_request(request)
    facets = _INTEGRATION_FACETS.get(w["id"]) if w else None

    catalog: list[dict[str, Any]] = []
    # Best-effort: try the live marketplace model first.
    try:
        from apps.integrations_marketplace.models import Connector
        qs = Connector.objects.all()  # tenant-isolation-allow: platform-wide-connector-catalog-not-tenant-scoped
        for c in qs[:200]:
            catalog.append({
                "id": c.pk,
                "slug": getattr(c, "slug", "") or "",
                "name": getattr(c, "name", "") or "",
                "category": (getattr(c, "category", "") or "").lower(),
                "vendor": getattr(c, "vendor", "") or "",
            })
    except Exception:  # noqa: BLE001
        # Static fallback so the page is useful in dev.
        catalog = [
            {"id": 1, "slug": "canvas", "name": "Canvas LMS", "category": "lms", "vendor": "Instructure"},
            {"id": 2, "slug": "moodle", "name": "Moodle", "category": "lms", "vendor": "Moodle HQ"},
            {"id": 3, "slug": "google-classroom", "name": "Google Classroom", "category": "lms", "vendor": "Google"},
            {"id": 4, "slug": "schoology", "name": "Schoology", "category": "lms", "vendor": "PowerSchool"},
            {"id": 5, "slug": "clever", "name": "Clever", "category": "identity", "vendor": "Clever"},
            {"id": 6, "slug": "classlink", "name": "ClassLink", "category": "identity", "vendor": "ClassLink"},
            {"id": 7, "slug": "azure-ad", "name": "Microsoft Entra ID", "category": "identity", "vendor": "Microsoft"},
            {"id": 8, "slug": "okta", "name": "Okta", "category": "identity", "vendor": "Okta"},
            {"id": 9, "slug": "stripe", "name": "Stripe", "category": "billing", "vendor": "Stripe"},
            {"id": 10, "slug": "twilio", "name": "Twilio", "category": "messaging", "vendor": "Twilio"},
        ]

    rows = catalog
    if facets:
        wanted_domain = facets.get("domain", "")
        if wanted_domain:
            rows = [r for r in catalog if r["category"] == wanted_domain]

    if _wants_json(request):
        return JsonResponse({
            "success": True,
            "wedge": w["id"] if w else None,
            "facets": facets,
            "count": len(rows),
            "rows": rows,
        })
    return render(request, "super/wedges/surface_integrations.html", {
        "wedge": w,
        "rows": rows,
        "facets": facets,
        "total": len(rows),
        "is_filtered": facets is not None,
    })


# ----- 3) Grading scales surface ------------------------------------------


@staff_member_required
@require_http_methods(["GET"])
def institution_types_by_wedge(request):
    """Institution-type registry picker filtered by ``?wedge=<id>``.

    Surfaces the authorizers / IB+Cambridge programmes / faith
    traditions per the v4.00.38 institution-type SOT. Honors
    ``?format=json`` like the sibling surfaces.
    """
    try:
        from apps.siteconfig._institution_types import picker_for_wedge, INSTITUTION_TYPES
    except Exception as exc:  # noqa: BLE001
        logger.warning("institution types unavailable: %s", exc)
        picker_for_wedge = lambda wid: {"institution": {}, "kind": "type-only", "rows": []}
        INSTITUTION_TYPES = {}

    w = _wedge_from_request(request)
    picker: dict[str, Any]
    if w is None:
        picker = {"institution": {}, "kind": "all-types", "rows": [
            {"code": v["code"], "label": v["label"], "wedge_id": k}
            for k, v in INSTITUTION_TYPES.items()
        ]}
    else:
        picker = picker_for_wedge(w["id"])

    if _wants_json(request):
        return JsonResponse({
            "success": True,
            "wedge": w["id"] if w else None,
            "picker": picker,
            "count": len(picker["rows"]),
        })
    return render(request, "super/wedges/surface_institution_types.html", {
        "wedge": w,
        "picker": picker,
        "rows": picker["rows"],
        "total": len(picker["rows"]),
        "is_filtered": w is not None,
    })


@staff_member_required
@require_http_methods(["GET"])
def grading_scales_by_wedge(request):
    """Grading scales filtered by ``?wedge=<id>``."""
    try:
        from apps.siteconfig._grading_bands import UNIVERSAL_SCALES, SYSTEM_TYPE_BANDS
    except Exception as exc:  # noqa: BLE001
        logger.warning("grading bands unavailable: %s", exc)
        UNIVERSAL_SCALES, SYSTEM_TYPE_BANDS = [], {}

    w = _wedge_from_request(request)
    delivery = _GRADING_DELIVERY.get(w["id"]) if w else None

    # Surface all named scales — both universal + per-system-type.
    rows: list[dict[str, Any]] = []
    for scale in UNIVERSAL_SCALES:
        rows.append({
            "kind": "universal",
            "code": scale.get("code", ""),
            "label": scale.get("label", ""),
            "delivery_tag": "universal",
        })
    for st_code, band in SYSTEM_TYPE_BANDS.items():
        rows.append({
            "kind": "system_type",
            "code": st_code,
            "label": (band or {}).get("label") or st_code,
            "delivery_tag": (band or {}).get("delivery_tag", st_code),
        })

    if delivery:
        rows = [r for r in rows if delivery in (r["code"], r["delivery_tag"]) or delivery in r["label"].lower()]

    if _wants_json(request):
        return JsonResponse({
            "success": True,
            "wedge": w["id"] if w else None,
            "delivery": delivery,
            "count": len(rows),
            "rows": rows,
        })
    return render(request, "super/wedges/surface_grading.html", {
        "wedge": w,
        "rows": rows,
        "delivery": delivery,
        "total": len(rows),
        "is_filtered": delivery is not None,
    })
