"""
Super wedge surfaces: Tier A (1–6) plus geography (7–13), education systems (14–22),
learning delivery & institution types (23–43), ministry stubs, group campuses (22), etc.

Operator checklists: ``?wedge=`` on geography, education_systems, learning_delivery_packs,
ministry_report_stubs; fixed wedges where the page is single-wedge scoped.
"""

import json
from urllib.parse import quote, urlencode

from django.http import Http404, HttpResponseBadRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, NoReverseMatch


def _safe_reverse(name, *args, **kwargs):
    try:
        return reverse(name, *args, **kwargs)
    except NoReverseMatch:
        return None


def _beachhead_checklist(wedge_id: int):
    from apps.platform_runtime.beachhead_operator_checklists import (
        build_resolved_beachhead_checklist,
    )

    return build_resolved_beachhead_checklist(wedge_id, _safe_reverse)


def _operator_wedge_from_query(request, *, default: int, lo: int, hi: int) -> int:
    raw = (request.GET.get("wedge") or "").strip()
    if raw.isdigit():
        v = int(raw)
        if lo <= v <= hi:
            return v
    return default


def _operator_wedge_from_query_allowed(
    request, *, default: int, allowed: frozenset[int]
) -> int:
    raw = (request.GET.get("wedge") or "").strip()
    if raw.isdigit():
        v = int(raw)
        if v in allowed:
            return v
    return default


def _wedge_switcher_links_for_wedges(
    request,
    *,
    url_name: str,
    wedges: tuple[int, ...],
    default_wedge: int,
    label_for_wedge: dict[int, str] | None = None,
) -> list[dict[str, object]]:
    """Build ?wedge= links for a non-contiguous set of wedge ids (e.g. 1 and 3 on curriculum)."""
    try:
        base = reverse(url_name)
    except NoReverseMatch:
        return []
    allowed = frozenset(wedges)
    active = _operator_wedge_from_query_allowed(
        request, default=default_wedge, allowed=allowed
    )
    out: list[dict[str, object]] = []
    for w in wedges:
        sep = "&" if "?" in base else "?"
        href = f"{base}{sep}wedge={w}"
        label = (label_for_wedge or {}).get(w, f"W{w}")
        out.append({"wedge": w, "label": label, "href": href, "active": w == active})
    return out


def _wedge_switcher_links(
    request,
    *,
    url_name: str,
    lo: int,
    hi: int,
    label_for_wedge: dict[int, str] | None = None,
) -> list[dict[str, object]]:
    """Build ?wedge= navigation for operator checklist (manager host)."""
    try:
        base = reverse(url_name)
    except NoReverseMatch:
        return []
    active = _operator_wedge_from_query(request, default=lo, lo=lo, hi=hi)
    out: list[dict[str, object]] = []
    for w in range(lo, hi + 1):
        sep = "&" if "?" in base else "?"
        href = f"{base}{sep}wedge={w}"
        label = (label_for_wedge or {}).get(w, f"W{w}")
        out.append({"wedge": w, "label": label, "href": href, "active": w == active})
    return out


def _get_wedge_line_row(wedge_id: int):
    from apps.platform_runtime.wedge_line_registry import WEDGE_LINES

    for r in WEDGE_LINES:
        if int(r["id"]) == wedge_id:
            return r
    return None


def _operator_deep_links(wedge_id: int) -> list[dict[str, str]]:
    """Human grouping surfaces (often with ?wedge=) from canonical wedge id."""
    out: list[dict[str, str]] = []

    def add(label: str, viewname: str, params: dict[str, str] | None = None) -> None:
        base = _safe_reverse(viewname)
        if not base:
            return
        if params:
            sep = "&" if "?" in base else "?"
            out.append(
                {"label": label, "href": f"{base}{sep}{urlencode(params)}"}
            )
        else:
            out.append({"label": label, "href": base})

    if wedge_id in (1, 3):
        add(
            "Curriculum & region packs",
            "super:curriculum_packs",
            {"wedge": str(wedge_id)},
        )
    elif wedge_id == 2:
        add("One SIS, any LMS", "super:one_sis_any_lms")
    elif wedge_id == 4:
        add("District & enterprise", "super:district_enterprise")
    elif wedge_id == 5:
        add("Advancement hub", "super:advancement_hub")
    elif wedge_id == 6:
        add("Higher-ed pack", "super:he_pack")
    elif 7 <= wedge_id <= 13:
        add("Geography hub", "super:geography", {"wedge": str(wedge_id)})
    elif 14 <= wedge_id <= 22:
        add("Education systems", "super:education_systems", {"wedge": str(wedge_id)})
        if wedge_id == 22:
            add("Group & campuses", "super:group_campuses")
    elif 23 <= wedge_id <= 43:
        add(
            "Learning delivery & institution types",
            "super:learning_delivery_packs",
            {"wedge": str(wedge_id)},
        )
        if wedge_id >= 31:
            add(
                "Ministry report stubs",
                "super:ministry_report_stubs",
                {"wedge": str(wedge_id)},
            )
    elif wedge_id == 44:
        add("One SIS, any LMS", "super:one_sis_any_lms")
        add("Native Clever / ClassLink console", "super:native_roster_connectors")
    elif wedge_id == 45:
        add("Trust center", "super:trust_center")
    return out


def super_ministry_report_stubs(request):
    """Per institution type: ministry / accreditation report stub catalog (Phase J+)."""
    from apps.platform_runtime.learning_institution_catalog import (
        INSTITUTION_TYPE_PACKS,
        INSTITUTION_TYPE_STATUTORY_COUNTRY_HINT,
        MINISTRY_REPORT_STUBS,
    )

    pdf_preview = _safe_reverse("super:ministry_stub_pdf")
    country_hint = INSTITUTION_TYPE_STATUTORY_COUNTRY_HINT
    rows = []
    for pack in INSTITUTION_TYPE_PACKS:
        code = pack["code"]
        stubs = MINISTRY_REPORT_STUBS.get(code) or MINISTRY_REPORT_STUBS.get(
            "DEFAULT", []
        )
        cc = country_hint.get(code, "")
        enriched = []
        for s in stubs:
            slug = (s.get("slug") or "").strip()
            enriched.append(
                {
                    **s,
                    "pdf_preview_url": (
                        f"{pdf_preview}?stub={quote(slug)}&country={quote(cc)}"
                        if pdf_preview and slug and cc
                        else (
                            f"{pdf_preview}?stub={quote(slug)}"
                            if pdf_preview and slug
                            else None
                        )
                    ),
                    "suggested_country": cc,
                }
            )
        rows.append({**pack, "stubs": enriched})
    min_wedge = _operator_wedge_from_query(request, default=31, lo=31, hi=43)
    return render(
        request,
        "schools/super_ministry_report_stubs.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "rows": rows,
            "learning_packs_url": _safe_reverse("super:learning_delivery_packs"),
            "statutory_hints_url": _safe_reverse("super:learning_institution_catalog_json"),
            "tenant_statutory_extract_path": "/api/learning/statutory-extract/",
            "tenant_identity_graph_path": "/api/learning/identity-graph-summary/",
            "beachhead_checklist": _beachhead_checklist(min_wedge),
            "beachhead_wedge_id": min_wedge,
            "operator_wedge_switcher": _wedge_switcher_links(
                request,
                url_name="super:ministry_report_stubs",
                lo=31,
                hi=43,
            ),
        },
    )


def super_ministry_stub_pdf(request):
    """Manager-host ministry stub PDF (same bytes as tenant API) — super access only."""
    stub = (request.GET.get("stub") or "").strip()
    if not stub or not stub.replace("_", "").isalnum():
        return HttpResponseBadRequest("Invalid stub")
    country = (request.GET.get("country") or request.GET.get("jurisdiction") or "").strip()
    from apps.platform_runtime.learning_institution_catalog import MINISTRY_REPORT_STUBS

    label = stub
    for _k, rows in MINISTRY_REPORT_STUBS.items():
        for r in rows or []:
            if r.get("slug") == stub:
                label = r.get("label") or stub
                break
    try:
        from apps.platform_runtime.ministry_stub_pdf import build_ministry_stub_pdf_bytes
    except ImportError:
        return HttpResponse("PDF engine unavailable", status=503)
    try:
        pdf = build_ministry_stub_pdf_bytes(
            stub,
            label,
            school_name="Manager preview (no tenant)",
            country_code=country or None,
        )
    except ImportError:
        return HttpResponse("PDF engine unavailable", status=503)
    cc = (country or "").strip().upper()[:2]
    suffix = f"_{cc}" if cc else ""
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = (
        f'attachment; filename="ministry_{stub}{suffix}.pdf"'
    )
    return resp


def super_district_enterprise(request):
    """Wedge 4: District / ERP operator surface — decision links, not a toggle wall."""
    from apps.interop import erp_coexistence
    from apps.platform_runtime.identity_graph_rollups import (
        compute_platform_identity_rollups,
    )

    erp_sample = erp_coexistence.sample_webhook_envelope(
        event="enrollment.synced",
        school_id="demo-school",
    )
    return render(
        request,
        "schools/super_district_enterprise.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "trust_center_url": _safe_reverse("super:trust_center"),
            "schools_list_url": _safe_reverse("super:schools_list"),
            "group_campuses_url": _safe_reverse("super:group_campuses"),
            "migration_cloud_url": _safe_reverse("super:migration_cloud"),
            "one_sis_url": _safe_reverse("super:one_sis_any_lms"),
            "apicenter_url": _safe_reverse("apicenter:dashboard"),
            "billing_url": _safe_reverse("super:billing_dashboard"),
            "geography_url": _safe_reverse("super:geography"),
            "education_systems_url": _safe_reverse("super:education_systems"),
            "analytics_url": _safe_reverse("super:analytics_overview"),
            "usage_url": _safe_reverse("super:usage"),
            "government_aggregates_path": "/api/government/aggregates/",
            "platform_rollups": compute_platform_identity_rollups(),
            "beachhead_checklist": _beachhead_checklist(4),
            "beachhead_wedge_id": 4,
            "erp_coexistence_patterns": erp_coexistence.list_patterns(),
            "erp_webhook_sample_json": json.dumps(erp_sample, indent=2),
            "native_roster_connectors_url": _safe_reverse(
                "super:native_roster_connectors"
            ),
            "wedge_index_url": _safe_reverse("super:wedge_index"),
        },
    )


def super_learning_institution_catalog_json(request):
    """Machine-readable catalog for partners / Studio automation (23–43)."""
    from django.http import JsonResponse

    from apps.platform_runtime.learning_institution_catalog import (
        CATALOG_VERSION,
        INSTITUTION_TYPE_PACKS,
        INSTITUTION_TYPE_STATUTORY_COUNTRY_HINT,
        LEARNING_DELIVERY_MODES,
        MINISTRY_REPORT_STUBS,
        STATUTORY_JURISDICTION_HINTS,
        TERMINOLOGY_PACKS,
    )

    return JsonResponse(
        {
            "catalog_version": CATALOG_VERSION,
            "learning_delivery_modes": LEARNING_DELIVERY_MODES,
            "institution_type_packs": INSTITUTION_TYPE_PACKS,
            "ministry_report_stubs": MINISTRY_REPORT_STUBS,
            "statutory_jurisdiction_hints": STATUTORY_JURISDICTION_HINTS,
            "institution_type_statutory_country_hint": INSTITUTION_TYPE_STATUTORY_COUNTRY_HINT,
            "terminology_locales": list(TERMINOLOGY_PACKS.keys()),
            "version": 1,
        },
        json_dumps_params={"indent": 2},
    )


def super_learning_delivery_packs(request):
    """Wedges 23–30 / 31–43 catalog: delivery modes + institution-type pack mapping."""
    from apps.platform_runtime.learning_institution_catalog import (
        INSTITUTION_TYPE_PACKS,
        LEARNING_DELIVERY_MODES,
    )

    ld_wedge = _operator_wedge_from_query(request, default=23, lo=23, hi=43)
    return render(
        request,
        "schools/super_learning_delivery_packs.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "delivery_modes": LEARNING_DELIVERY_MODES,
            "institution_types": INSTITUTION_TYPE_PACKS,
            "curriculum_packs_url": _safe_reverse("super:curriculum_packs"),
            "education_systems_url": _safe_reverse("super:education_systems"),
            "one_sis_url": _safe_reverse("super:one_sis_any_lms"),
            "catalog_json_url": _safe_reverse(
                "super:learning_institution_catalog_json"
            ),
            "beachhead_checklist": _beachhead_checklist(ld_wedge),
            "beachhead_wedge_id": ld_wedge,
            "operator_wedge_switcher": _wedge_switcher_links(
                request,
                url_name="super:learning_delivery_packs",
                lo=23,
                hi=43,
            ),
        },
    )


def super_curriculum_packs(request):
    """Starter & region packs — W1 and W3 operator checklists (?wedge=1|3); DNA + REGIONAL_POLICY_PACKS."""
    from apps.platform_runtime.wedge_line_registry import BEACHHEAD_BLUEPRINT_PACKS
    from apps.siteconfig.education_dna import EDUCATION_DNA_CURRICULUMS
    from apps.siteconfig.tenant_config import REGIONAL_POLICY_PACKS

    _names = {
        "british_igcse": "British / IGCSE",
        "west_african_waec": "West African WAEC",
        "francophone_bac": "Francophone Bac",
        "american": "American",
        "vocational": "Vocational",
        "ib": "IB",
    }
    curriculum_list = [
        {"code": code, "name": _names.get(code, code.replace("_", " ").title())}
        for code, data in EDUCATION_DNA_CURRICULUMS.items()
    ]
    region_list = [
        {"code": pack["code"], "name": pack.get("name", pack["code"])}
        for pack in REGIONAL_POLICY_PACKS.values()
    ]
    create_school_url = _safe_reverse("super:create_school_wizard")
    setup_studio_url = _safe_reverse("siteconfig:guided_onboarding")
    launch_studio_url = _safe_reverse("studio_os:launch")
    geography_url = _safe_reverse("super:geography")
    uk_statutory_reports_url = _safe_reverse(
        "siteconfig:report_library"
    ) or _safe_reverse("reports:report_list")
    trust_center_url = _safe_reverse("super:trust_center")
    migration_cloud_url = _safe_reverse("super:migration_cloud")
    one_sis_url = _safe_reverse("super:one_sis_any_lms")
    learning_delivery_url = _safe_reverse("super:learning_delivery_packs")
    blueprints_catalog_url = _safe_reverse("super:blueprints_catalog")
    # W1 (international K-12) and W3 (UK / British) both map to this surface per wedge_line_registry.
    curriculum_checklist_wedges = (1, 3)
    cur_wedge = _operator_wedge_from_query_allowed(
        request, default=1, allowed=frozenset(curriculum_checklist_wedges)
    )
    return render(
        request,
        "schools/super_curriculum_packs.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "curriculum_list": curriculum_list,
            "region_list": region_list,
            "create_school_url": create_school_url,
            "setup_studio_url": setup_studio_url,
            "launch_studio_url": launch_studio_url,
            "geography_url": geography_url,
            "uk_statutory_name": "UK statutory pack",
            "uk_statutory_reports_url": uk_statutory_reports_url,
            "trust_center_url": trust_center_url,
            "migration_cloud_url": migration_cloud_url,
            "one_sis_url": one_sis_url,
            "learning_delivery_url": learning_delivery_url,
            "beachhead_blueprint_packs": list(BEACHHEAD_BLUEPRINT_PACKS),
            "blueprints_catalog_url": blueprints_catalog_url,
            "beachhead_checklist": _beachhead_checklist(cur_wedge),
            "beachhead_wedge_id": cur_wedge,
            "operator_wedge_switcher": _wedge_switcher_links_for_wedges(
                request,
                url_name="super:curriculum_packs",
                wedges=curriculum_checklist_wedges,
                default_wedge=1,
                label_for_wedge={
                    1: "W1 International K-12",
                    3: "W3 UK / British",
                },
            ),
        },
    )


def super_one_sis_any_lms(request):
    """Wedge 2: One SIS, any LMS — shipped guided flow: configure → SSO → roster → grade passback; certified LMS status."""
    from apps.platform_runtime.lms_certification_registry import as_template_rows

    integration_url = _safe_reverse("siteconfig:integration_catalog") or _safe_reverse(
        "apicenter:dashboard"
    )
    onboarding_url = _safe_reverse("siteconfig:guided_onboarding")
    migration_cloud_url = _safe_reverse("super:migration_cloud")
    trust_center_url = _safe_reverse("super:trust_center")
    curriculum_packs_url = _safe_reverse("super:curriculum_packs")
    geography_url = _safe_reverse("super:geography")
    lms_certification = as_template_rows()
    return render(
        request,
        "schools/super_one_sis_any_lms.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "integration_url": integration_url,
            "onboarding_url": onboarding_url,
            "migration_cloud_url": migration_cloud_url,
            "trust_center_url": trust_center_url,
            "curriculum_packs_url": curriculum_packs_url,
            "geography_url": geography_url,
            "lms_certification": lms_certification,
            "native_roster_connectors_url": _safe_reverse(
                "super:native_roster_connectors"
            ),
            "wedge_44_url": _safe_reverse(
                "super:wedge_operator_detail", kwargs={"wedge_id": 44}
            ),
            "beachhead_checklist": _beachhead_checklist(2),
            "beachhead_wedge_id": 2,
            "secondary_operator_checklist": _beachhead_checklist(44),
            "secondary_operator_wedge_id": 44,
        },
    )


def super_advancement_hub(request):
    """Wedge 5: Advancement — Alumni, campaigns, aid; Phase 2 donor/campaign/gift/receipt; identity graph."""
    alumni_list_url = _safe_reverse("accounts:backend_alumni_list")
    campaigns_url = _safe_reverse(
        "communication:group_list"
    )  # or broadcast list if exists
    aid_services_url = _safe_reverse("finance:dashboard")
    phase2_placeholder_url = reverse("super:advancement_phase2_placeholder")
    return render(
        request,
        "schools/super_advancement_hub.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "alumni_list_url": alumni_list_url,
            "campaigns_url": campaigns_url,
            "aid_services_url": aid_services_url,
            "phase2_placeholder_url": phase2_placeholder_url,
            "tenant_donor_crm_path": "/authentication/backend/advancement/donors/",
            "beachhead_checklist": _beachhead_checklist(5),
            "beachhead_wedge_id": 5,
        },
    )


def super_advancement_phase2_placeholder(request):
    """Phase 2 advancement: donors + gifts (CRM v1); super-only."""
    from decimal import Decimal, InvalidOperation

    from django.contrib import messages
    from django.utils import timezone

    from apps.schools.models import AdvancementDonor, AdvancementGift, School

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "add_donor":
            sid = (request.POST.get("school_id") or "").strip()
            name = (request.POST.get("display_name") or "").strip()
            school_obj = (
                School.objects.filter(pk=sid, is_active=True).first() if sid else None
            )
            if school_obj and name:
                AdvancementDonor.objects.create(
                    school=school_obj,
                    display_name=name[:200],
                    email=(request.POST.get("email") or "").strip()[:254],
                    external_ref=(request.POST.get("external_ref") or "").strip()[:120],
                )
                messages.success(request, "Donor created.")
            else:
                messages.error(request, "Valid school_id and display_name required.")
        elif action == "add_gift":
            did = (request.POST.get("donor_id") or "").strip()
            amt = (request.POST.get("amount") or "").strip()
            if did.isdigit() and amt:
                try:
                    d = Decimal(amt)
                    if d > 0:
                        donor = AdvancementDonor.objects.filter(pk=int(did)).first()
                        if donor:
                            AdvancementGift.objects.create(
                                donor=donor,
                                amount=d,
                                currency=(
                                    request.POST.get("currency") or "USD"
                                ).strip()[:3]
                                or "USD",
                                received_at=timezone.now().date(),
                                notes=(request.POST.get("gift_notes") or "").strip()[
                                    :500
                                ],
                            )
                            messages.success(request, "Gift recorded.")
                        else:
                            messages.error(request, "Donor not found.")
                    else:
                        messages.error(request, "Amount must be positive.")
                except (InvalidOperation, ValueError):
                    messages.error(request, "Invalid amount.")
            else:
                messages.error(request, "donor_id and amount required.")
        return redirect(request.path)

    donors = list(
        AdvancementDonor.objects.select_related("school").order_by("-updated_at")[:80]
    )
    gifts = list(
        AdvancementGift.objects.select_related("donor", "donor__school").order_by(
            "-received_at", "-pk"
        )[:80]
    )
    schools = list(School.objects.filter(is_active=True).order_by("name")[:200])
    return render(
        request,
        "schools/super_advancement_phase2_placeholder.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "advancement_hub_url": reverse("super:advancement_hub"),
            "donors": donors,
            "gifts": gifts,
            "schools": schools,
            "phase2_live": True,
        },
    )


def super_he_pack(request):
    """Wedge 6: HE pack as cohesive product — degree_audit, enrollment, catalog; months-not-years."""
    plans_url = _safe_reverse("super:plans_list")
    catalog_json_url = _safe_reverse("super:learning_institution_catalog_json")
    learning_delivery_url = _safe_reverse("super:learning_delivery_packs")
    curriculum_packs_url = _safe_reverse("super:curriculum_packs")
    return render(
        request,
        "schools/super_he_pack.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "plans_url": plans_url,
            "catalog_json_url": catalog_json_url,
            "learning_delivery_url": learning_delivery_url,
            "curriculum_packs_url": curriculum_packs_url,
            "beachhead_checklist": _beachhead_checklist(6),
            "beachhead_wedge_id": 6,
        },
    )


def super_geography(request):
    """Wedges 7–13: Region packs by continent — Africa, Asia, Europe, North America, South America, Oceania, MENA."""
    from apps.siteconfig.tenant_config import REGIONAL_POLICY_PACKS

    # Map continent (wedge 7–13) to pack codes that belong to it
    continent_packs = [
        {
            "wedge": 7,
            "continent": "Africa",
            "codes": ["LCA", "WAEC", "AFR_FR"],
            "description": "LCA (low-connectivity), WAEC (Anglophone West Africa), Francophone Africa.",
        },
        {
            "wedge": 8,
            "continent": "Asia",
            "codes": ["ASIA"],
            "description": "Asia Education Pack; national curricula and ministry reporting.",
        },
        {
            "wedge": 9,
            "continent": "Europe (beyond UK)",
            "codes": ["EU", "GBR"],
            "description": "EU pack (FRA, DEU, etc.); UK/GBR (wedge 3).",
        },
        {
            "wedge": 10,
            "continent": "North America",
            "codes": ["US", "CAN"],
            "description": "United States and Canada; FERPA, PIPEDA.",
        },
        {
            "wedge": 11,
            "continent": "South America",
            "codes": ["BRA", "LATAM_ES"],
            "description": "Brazil (BRA); Spanish South America (ARG, COL, CHL, etc.).",
        },
        {
            "wedge": 12,
            "continent": "Oceania",
            "codes": ["AUS", "NZL"],
            "description": "Australia and New Zealand; national curricula and statutory.",
        },
        {
            "wedge": 13,
            "continent": "MENA",
            "codes": ["MENA"],
            "description": "Middle East & North Africa; AR/EN/FR; ministry and calendar.",
        },
    ]
    create_school_url = _safe_reverse("super:create_school_wizard")
    geography_list = []
    for item in continent_packs:
        packs = []
        for c in item["codes"]:
            if c not in REGIONAL_POLICY_PACKS:
                continue
            raw = REGIONAL_POLICY_PACKS[c]
            defs = raw.get("defaults") or {}
            create_school_with_pack_url = (
                (create_school_url + "?pack=" + quote(c)) if create_school_url else None
            )
            packs.append(
                {
                    "code": c,
                    "name": raw.get("name", c),
                    "currency": defs.get("currency", "—"),
                    "language": defs.get("default_language", "—"),
                    "grading_scale": defs.get("grading_scale", "—"),
                    "data_residency": defs.get("data_residency_region", "—"),
                    "privacy_framework": defs.get("privacy_framework", "—"),
                    "is_rtl": bool(defs.get("rtl", False)),
                    "create_school_with_pack_url": create_school_with_pack_url,
                }
            )
        geography_list.append(
            {
                "wedge": item["wedge"],
                "continent": item["continent"],
                "packs": packs,
                "description": item["description"],
            }
        )
    # Side-by-side compare (Wedges 7–13 world-class): anchor English-speaking North Atlantic + UK
    compare_codes = ("US", "CAN", "GBR")
    pack_compare_rows = []
    for c in compare_codes:
        if c not in REGIONAL_POLICY_PACKS:
            continue
        raw = REGIONAL_POLICY_PACKS[c]
        defs = raw.get("defaults") or {}
        pack_compare_rows.append(
            {
                "code": c,
                "name": raw.get("name", c),
                "currency": defs.get("currency", "—"),
                "language": defs.get("default_language", "—"),
                "grading_scale": defs.get("grading_scale", "—"),
                "data_residency": defs.get("data_residency_region", "—"),
                "privacy_framework": defs.get("privacy_framework", "—"),
                "create_school_with_pack_url": (
                    (create_school_url + "?pack=" + quote(c)) if create_school_url else None
                ),
            }
        )
    setup_studio_url = _safe_reverse("siteconfig:guided_onboarding")
    curriculum_packs_url = _safe_reverse("super:curriculum_packs")
    trust_center_url = _safe_reverse("super:trust_center")
    geo_wedge = _operator_wedge_from_query(request, default=7, lo=7, hi=13)
    geo_labels = {
        7: "W7 Africa",
        8: "W8 Asia",
        9: "W9 Europe",
        10: "W10 N. America",
        11: "W11 S. America",
        12: "W12 Oceania",
        13: "W13 MENA",
    }
    return render(
        request,
        "schools/super_geography.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "geography_list": geography_list,
            "create_school_url": create_school_url,
            "setup_studio_url": setup_studio_url,
            "curriculum_packs_url": curriculum_packs_url,
            "trust_center_url": trust_center_url,
            "beachhead_checklist": _beachhead_checklist(geo_wedge),
            "beachhead_wedge_id": geo_wedge,
            "operator_wedge_switcher": _wedge_switcher_links(
                request,
                url_name="super:geography",
                lo=7,
                hi=13,
                label_for_wedge=geo_labels,
            ),
            "pack_compare_rows": pack_compare_rows,
        },
    )


def super_education_systems(request):
    """SOT §0.2.1: Wedges 14–22 — Education systems (Public, Private, Charter, International, etc.). Control-plane visibility and links."""
    from apps.registries.services import list_sector_system_types_14_22

    sector_list = list_sector_system_types_14_22()
    create_school_url = _safe_reverse("super:create_school_wizard")
    setup_studio_url = _safe_reverse("siteconfig:guided_onboarding")
    geography_url = _safe_reverse("super:geography")
    curriculum_packs_url = _safe_reverse("super:curriculum_packs")
    runtime_inspector_url = _safe_reverse("super:runtime_inspector")
    advancement_hub_url = _safe_reverse("super:advancement_hub")
    registries_url = _safe_reverse("super:registries_overview")
    # Ministry/statutory (14 Public, 20 Government): moe_presets and statutory reporting
    _out_studio = _safe_reverse("studio_os:output")
    report_library_url = (
        f"{_out_studio}?pane=reports"
        if _out_studio
        else _safe_reverse("reports:report_list")
    )
    # Multi-campus (22): hierarchy; link to schools list; wedge 14–22: segment by sector
    schools_list_url = _safe_reverse("super:schools_list")
    group_campuses_url = _safe_reverse("super:group_campuses")
    blueprints_catalog_url = _safe_reverse("super:blueprints_catalog")
    from apps.registries.services import (
        WEDGE_14_22_SECTOR_CODES,
        build_education_system_support_accordion,
    )

    sector_filtered_links = []
    if schools_list_url:
        for code in WEDGE_14_22_SECTOR_CODES:
            sep = "&" if "?" in schools_list_url else "?"
            sector_filtered_links.append(
                {
                    "code": code,
                    "name": code.replace("_", " ").title(),
                    "url": f"{schools_list_url}{sep}primary_sector={code}",
                }
            )
    from django.conf import settings

    playbook_url = getattr(settings, "CONTROL_PLANE_RUNBOOKS_URL", None) or getattr(
        settings, "WEDGE_14_22_OPERATOR_PLAYBOOK_URL", ""
    )
    support_by_sector = build_education_system_support_accordion(_safe_reverse)
    for s in support_by_sector:
        s["next_actions"] = [a for a in s["next_actions"] if a.get("url")]
    edu_wedge = _operator_wedge_from_query(request, default=14, lo=14, hi=22)
    return render(
        request,
        "schools/super_education_systems.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "sector_list": sector_list,
            "create_school_url": create_school_url,
            "setup_studio_url": setup_studio_url,
            "geography_url": geography_url,
            "curriculum_packs_url": curriculum_packs_url,
            "runtime_inspector_url": runtime_inspector_url,
            "advancement_hub_url": advancement_hub_url,
            "registries_url": registries_url,
            "report_library_url": report_library_url,
            "schools_list_url": schools_list_url,
            "group_campuses_url": group_campuses_url,
            "blueprints_catalog_url": blueprints_catalog_url,
            "sector_filtered_links": sector_filtered_links,
            "playbook_url": playbook_url,
            "support_by_sector": support_by_sector,
            "beachhead_checklist": _beachhead_checklist(edu_wedge),
            "beachhead_wedge_id": edu_wedge,
            "operator_wedge_switcher": _wedge_switcher_links(
                request,
                url_name="super:education_systems",
                lo=14,
                hi=22,
            ),
        },
    )


def super_group_campuses(request):
    """Wedge 22: Group & campuses — list hierarchy (parent_school_id / hierarchy_path), add campus to group."""
    from apps.schools.models import School

    # Groups: schools that have at least one child (root of a hierarchy)
    group_ids = set(
        School.objects.filter(parent_school_id__isnull=False)
        .values_list("parent_school_id", flat=True)
        .distinct()
    )
    groups_qs = School.objects.filter(pk__in=group_ids, is_active=True).order_by("name")
    groups_with_children = []
    create_school_url = _safe_reverse("super:create_school_wizard")
    for group in groups_qs:
        children = list(
            School.objects.filter(parent_school_id=group.pk, is_active=True)
            .order_by("name")
            .only("id", "name", "slug", "hierarchy_path")
        )
        add_campus_url = None
        if create_school_url:
            add_campus_url = f"{create_school_url}?parent_school_id={group.pk}"
        groups_with_children.append(
            {
                "group": group,
                "children": children,
                "add_campus_url": add_campus_url,
            }
        )
    # Standalone: no parent, no children
    standalone_ids = (
        set(
            School.objects.filter(
                parent_school_id__isnull=True, is_active=True
            ).values_list("id", flat=True)
        )
        - group_ids
    )
    standalone = list(
        School.objects.filter(pk__in=standalone_ids)
        .order_by("name")[:50]
        .only("id", "name", "slug")
    )
    schools_list_url = _safe_reverse("super:schools_list")
    education_systems_url = _safe_reverse("super:education_systems")
    return render(
        request,
        "schools/super_group_campuses.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "groups_with_children": groups_with_children,
            "standalone": standalone,
            "create_school_url": create_school_url,
            "schools_list_url": schools_list_url,
            "education_systems_url": education_systems_url,
            "beachhead_checklist": _beachhead_checklist(22),
            "beachhead_wedge_id": 22,
        },
    )


def super_wedge_index(request):
    """Canonical index: one stable URL per wedge (1–45) via wedge_operator_detail."""
    from apps.platform_runtime.wedge_line_registry import WEDGE_LINES

    wedge_rows = []
    for r in WEDGE_LINES:
        wid = int(r["id"])
        href = _safe_reverse("super:wedge_operator_detail", kwargs={"wedge_id": wid})
        wedge_rows.append(
            {
                "id": wid,
                "name": r["name"],
                "tier": r["tier"],
                "phase": r["phase"],
                "href": href,
            }
        )
    return render(
        request,
        "schools/super_wedge_index.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "wedge_rows": wedge_rows,
        },
    )


def super_wedge_operator_detail(request, wedge_id: int):
    """Standalone operator surface for a single wedge id (canonical /super/wedge/<id>/)."""
    if wedge_id < 1 or wedge_id > 45:
        raise Http404
    row = _get_wedge_line_row(wedge_id)
    if not row:
        raise Http404
    registry_urls: list[dict[str, str | None]] = []
    for name in row["urls"]:
        registry_urls.append({"name": name, "url": _safe_reverse(name)})
    canonical_url = _safe_reverse(
        "super:wedge_operator_detail", kwargs={"wedge_id": wedge_id}
    )
    return render(
        request,
        "schools/super_wedge_operator_detail.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "wedge_index_url": _safe_reverse("super:wedge_index"),
            "wedge": row,
            "wedge_id": wedge_id,
            "registry_urls": registry_urls,
            "deep_links": _operator_deep_links(wedge_id),
            "beachhead_checklist": _beachhead_checklist(wedge_id),
            "beachhead_wedge_id": wedge_id,
            "canonical_path": canonical_url,
            "native_roster_url": _safe_reverse("super:native_roster_connectors")
            if wedge_id == 44
            else None,
        },
    )


def super_native_roster_connectors(request):
    """Super-only: exercise Clever v3.1 + ClassLink OneRoster clients with district credentials."""
    import json

    from django.contrib import messages

    from apps.accounts.district_interop_native import (
        log_super_native_probe,
        super_native_roster_post_allow,
    )
    from apps.interop.clever_classlink_client import (
        classlink_list_courses,
        classlink_roster_ping,
        clever_list_schools,
        clever_list_sections,
        clever_list_users,
        clever_oauth_token_exchange,
    )

    clever_result = None
    classlink_result = None
    oauth_result = None
    if request.method == "POST":
        if not super_native_roster_post_allow(request.user.pk):
            messages.error(
                request,
                "Native roster console: hourly POST limit reached. Retry later.",
            )
        else:
            ct = (request.POST.get("clever_bearer") or "").strip()
            if ct:
                clever_result = {
                    "users": clever_list_users(ct, limit=5),
                    "schools": clever_list_schools(ct, limit=5),
                    "sections": clever_list_sections(ct, limit=5),
                }
            cl_tok = (request.POST.get("classlink_bearer") or "").strip()
            cl_base = (request.POST.get("classlink_base_url") or "").strip()
            if cl_tok:
                classlink_result = {
                    "ping": classlink_roster_ping(cl_tok, district_path=cl_base),
                    "courses": classlink_list_courses(cl_tok, district_path=cl_base),
                }
            c_id = (request.POST.get("clever_client_id") or "").strip()
            c_sec = (request.POST.get("clever_client_secret") or "").strip()
            code = (request.POST.get("clever_auth_code") or "").strip()
            redir = (request.POST.get("clever_redirect_uri") or "").strip()
            if c_id and c_sec and code and redir:
                oauth_result = clever_oauth_token_exchange(c_id, c_sec, code, redir)
            log_super_native_probe(
                user_id=request.user.pk,
                had_clever=bool(ct),
                had_classlink=bool(cl_tok),
                had_oauth=bool(c_id and c_sec and code and redir),
            )

    def _dump(obj: object | None) -> str | None:
        if obj is None:
            return None
        return json.dumps(obj, indent=2, default=str)[:12000]

    return render(
        request,
        "schools/super_native_roster_connectors.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "wedge_detail_url": _safe_reverse(
                "super:wedge_operator_detail", kwargs={"wedge_id": 44}
            ),
            "clever_result_json": _dump(clever_result),
            "classlink_result_json": _dump(classlink_result),
            "oauth_result_json": _dump(oauth_result),
        },
    )
