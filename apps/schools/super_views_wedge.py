"""
Wedge 1–6 world-class bar: curriculum packs, One SIS any LMS flow, advancement hub, HE pack.
Single pane; linked from control plane nav or Setup Studio.
"""

from urllib.parse import quote

from django.shortcuts import render
from django.urls import reverse, NoReverseMatch


def _safe_reverse(name, *args, **kwargs):
    try:
        return reverse(name, *args, **kwargs)
    except NoReverseMatch:
        return None


def super_ministry_report_stubs(request):
    """Per institution type: ministry / accreditation report stub catalog (Phase J+)."""
    from apps.platform_runtime.learning_institution_catalog import (
        INSTITUTION_TYPE_PACKS,
        MINISTRY_REPORT_STUBS,
    )

    rows = []
    for pack in INSTITUTION_TYPE_PACKS:
        code = pack["code"]
        stubs = MINISTRY_REPORT_STUBS.get(code) or MINISTRY_REPORT_STUBS.get(
            "DEFAULT", []
        )
        rows.append({**pack, "stubs": stubs})
    return render(
        request,
        "schools/super_ministry_report_stubs.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "rows": rows,
            "learning_packs_url": _safe_reverse("super:learning_delivery_packs"),
        },
    )


def super_learning_institution_catalog_json(request):
    """Machine-readable catalog for partners / Studio automation (23–43)."""
    from django.http import JsonResponse

    from apps.platform_runtime.learning_institution_catalog import (
        CATALOG_VERSION,
        INSTITUTION_TYPE_PACKS,
        LEARNING_DELIVERY_MODES,
        MINISTRY_REPORT_STUBS,
        TERMINOLOGY_PACKS,
    )

    return JsonResponse(
        {
            "catalog_version": CATALOG_VERSION,
            "learning_delivery_modes": LEARNING_DELIVERY_MODES,
            "institution_type_packs": INSTITUTION_TYPE_PACKS,
            "ministry_report_stubs": MINISTRY_REPORT_STUBS,
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
        },
    )


def super_curriculum_packs(request):
    """Wedge 1: Starter & region packs as product — education_dna + REGIONAL_POLICY_PACKS, discoverable."""
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
        },
    )


def super_one_sis_any_lms(request):
    """Wedge 2: One SIS, any LMS — shipped guided flow: configure → SSO → roster → grade passback; certified LMS status."""
    integration_url = _safe_reverse("siteconfig:integration_catalog") or _safe_reverse(
        "apicenter:dashboard"
    )
    onboarding_url = _safe_reverse("siteconfig:guided_onboarding")
    # Certification status per LMS (incremental; update as we certify)
    lms_certification = [
        {"name": "Google Classroom / Workspace", "status": "Certified"},
        {"name": "Microsoft Teams / 365", "status": "Certified"},
        {"name": "Canvas", "status": "Certified"},
        {"name": "D2L Brightspace", "status": "In progress"},
        {"name": "Moodle", "status": "Certified"},
        {"name": "Blackboard", "status": "In progress"},
    ]
    return render(
        request,
        "schools/super_one_sis_any_lms.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "integration_url": integration_url,
            "onboarding_url": onboarding_url,
            "lms_certification": lms_certification,
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
            if (
                sid.isdigit()
                and name
                and School.objects.filter(pk=int(sid), is_active=True).exists()
            ):
                AdvancementDonor.objects.create(
                    school_id=int(sid),
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
    return render(
        request,
        "schools/super_he_pack.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "plans_url": plans_url,
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
    setup_studio_url = _safe_reverse("siteconfig:guided_onboarding")
    curriculum_packs_url = _safe_reverse("super:curriculum_packs")
    trust_center_url = _safe_reverse("super:trust_center")
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
    report_library_url = _safe_reverse("siteconfig:report_library") or _safe_reverse(
        "reports:report_list"
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
        },
    )
