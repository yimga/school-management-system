"""
RunMyCampus marketing and SEO endpoints.
"""

from __future__ import annotations

import json
import os
import random
from copy import deepcopy
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.templatetags.static import static
from django.db import DatabaseError, OperationalError
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_protect

from apps.schools.domain_resolution_service import get_canonical_base_domain
from apps.schools.marketing_institution_premium import INSTITUTION_PREMIUM_LAYER
from apps.schools.marketing_page_definitions import (
    COMPARE_PAGE_DEFINITIONS,
    GETTING_STARTED_SIMULATOR_STEPS,
    INSTITUTION_LANDING_DEFINITIONS,
    MARKETING_PAGE_DEFINITIONS,
    MARKETING_PAGE_EXTRAS,
    MIGRATE_PAGE_DEFINITIONS,
    MIGRATION_SIMULATOR_SOURCES,
    ROLE_PAGE_DEFINITIONS,
    TOPICAL_LANDING_DEFINITIONS,
)
from apps.siteconfig.brand_registry import resolve_global_brand_context
from apps.siteconfig.global_catalog import GlobalGeoCatalog

# Region/variant reserved for A/B or regional content (file naming: slug.json or slug_region_variant.json).
MARKETING_CONTENT_DIR = os.path.join(
    getattr(settings, "BASE_DIR", os.getcwd()), "config", "marketing_content"
)
# Single source of truth: how many primary nav items show in the bar before "More" dropdown (IMPROVEMENTS_RUNBOOK 3.1).
MARKETING_NAVBAR_VISIBLE_COUNT = 6

_MARKETING_PAGE_TYPE_TEMPLATES: dict[str, str] = {
    "pricing": "marketing/pages/type_pricing.html",
    "contact": "marketing/pages/type_contact.html",
    "company": "marketing/pages/type_company.html",
    "resources": "marketing/pages/type_resources_hub.html",
    "platform": "marketing/pages/type_platform_hub.html",
    "demo": "marketing/pages/type_demo.html",
    "book-demo": "marketing/pages/type_demo.html",
}
# Differentiated platform capability pages (buyer-specific layouts + self-hosted mockups).
_MARKETING_PLATFORM_DIFFERENTIATED_TEMPLATES: dict[str, str] = {
    "platform-admissions": "marketing/pages/type_platform_admissions.html",
    "platform-fees-payments": "marketing/pages/type_platform_fees_payments.html",
    "platform-parent-portal": "marketing/pages/type_platform_parent_portal.html",
    "platform-teacher-portal": "marketing/pages/type_platform_teacher_portal.html",
}


def _marketing_page_type_template(slug: str) -> str | None:
    """Optional specialized layout shell (stack class + inner partial); default uses schools/marketing_page.html."""
    s = (slug or "").strip().lower()
    if s in _MARKETING_PAGE_TYPE_TEMPLATES:
        return _MARKETING_PAGE_TYPE_TEMPLATES[s]
    if s in _MARKETING_PLATFORM_DIFFERENTIATED_TEMPLATES:
        return _MARKETING_PLATFORM_DIFFERENTIATED_TEMPLATES[s]
    if s.startswith("platform-") and s != "platform":
        return "marketing/pages/type_platform_detail.html"
    return None


def _marketing_more_nav_mega_columns() -> list[dict]:
    """Premium mega panel for overflow 'More' nav (Compare, Marketplace, Developers, Contact, Company)."""

    def p(name: str, fallback: str, **kwargs) -> str:
        u = _safe_reverse(name, kwargs=kwargs if kwargs else None)
        return u if u != "#" else fallback

    return [
        {
            "title": "Explore",
            "links": [
                {
                    "label": "Compare",
                    "path": p("marketing_compare", "/compare/"),
                    "blurb": "Evaluation framing and architecture contrast for serious procurement.",
                },
                {
                    "label": "Marketplace",
                    "path": p("marketing_app_marketplace", "/app-marketplace/"),
                    "blurb": "Governed apps and packs—extend the OS without shadow IT sprawl.",
                },
                {
                    "label": "Developers",
                    "path": p("marketing_developers", "/developers/"),
                    "blurb": "REST, webhooks, and sandbox patterns for your integration roadmap.",
                },
            ],
        },
        {
            "title": "Connect",
            "links": [
                {
                    "label": "Contact",
                    "path": p("marketing_contact", "/contact/"),
                    "blurb": "Sales, implementation, support, and partnerships—routed with clear expectations.",
                },
                {
                    "label": "Company",
                    "path": p("marketing_company", "/company/"),
                    "blurb": "How we work with schools, networks, and operators at scale.",
                },
            ],
        },
    ]


def _load_marketing_page_from_file(
    slug: str,
    region: str | None = None,
    variant: str | None = None,
) -> tuple[dict, dict] | None:
    """
    Load marketing page content from config/marketing_content/{slug}.json.
    Returns (page_dict, extras_dict) compatible with marketing_page template, or None if file missing/invalid.
    Region/variant: ``slug_region_variant.json``, ``slug_region.json``, ``slug_variant.json`` (no region),
    then ``slug.json``. Set ``MARKETING_CONTENT_REGION`` / ``MARKETING_CONTENT_VARIANT`` in settings.
    """
    slug = (slug or "").strip().lower()
    if not slug:
        return None
    # Most specific first: slug_region_variant, slug_region, slug_variant (campaign/A-B file), slug
    region = (region or "").strip().lower() or None
    variant = (variant or "").strip().lower() or None
    candidates: list[str] = []
    if region and variant:
        candidates.append(f"{slug}_{region}_{variant}.json")
    if region:
        candidates.append(f"{slug}_{region}.json")
    if variant:
        candidates.append(f"{slug}_{variant}.json")
    candidates.append(f"{slug}.json")
    for filename in candidates:
        path = os.path.join(MARKETING_CONTENT_DIR, filename)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        # Build page dict: label, seo_title, seo_description, headline, subheadline, schema_type, segments
        page = {
            "label": data.get("label", ""),
            "seo_title": data.get("seo_title", ""),
            "seo_description": data.get("seo_description", ""),
            "headline": data.get("headline", ""),
            "subheadline": data.get("subheadline", ""),
            "schema_type": data.get("schema_type", "WebPage"),
            "segments": data.get("segments")
            if isinstance(data.get("segments"), list)
            else [],
        }
        extras = data.get("extras")
        if not isinstance(extras, dict):
            extras = {}
        return (page, extras)
    return None


def _marketing_content_file_params() -> tuple[str | None, str | None]:
    """Region/variant for config/marketing_content file naming (see _load_marketing_page_from_file)."""
    reg = getattr(settings, "MARKETING_CONTENT_REGION", None)
    var = getattr(settings, "MARKETING_CONTENT_VARIANT", None)
    reg_s = reg.strip().lower() if isinstance(reg, str) and reg.strip() else None
    var_s = var.strip().lower() if isinstance(var, str) and var.strip() else None
    return reg_s, var_s


def _navbar_mega_columns_from_children(
    children: list[dict], column_titles: tuple[str, ...]
) -> list[dict]:
    """Split flat {label, path} nav children into mega menu columns for marketing_header.html."""
    if not children or not column_titles:
        return []
    ncols = len(column_titles)
    total = len(children)
    base, extra = divmod(total, ncols)
    cols: list[dict] = []
    idx = 0
    for ci, title in enumerate(column_titles):
        take = base + (1 if ci < extra else 0)
        chunk = children[idx : idx + take]
        idx += take
        cols.append(
            {
                "title": title,
                "links": [
                    {
                        "label": c["label"],
                        "path": c["path"],
                        "blurb": (c.get("blurb") or "") if isinstance(c, dict) else "",
                    }
                    for c in chunk
                ],
            }
        )
    return cols


def _nav_mega_link(label: str, path: str, blurb: str) -> dict:
    """One mega-menu row: title, href, one-line value prop."""
    return {"label": label, "path": path, "blurb": blurb}


def _safe_reverse(name: str, *, kwargs: dict | None = None) -> str:
    try:
        return reverse(name, kwargs=kwargs)
    except (NoReverseMatch, ValueError, TypeError):
        return "#"


def _marketing_nav() -> list[dict]:
    return [
        {"slug": slug, "label": page["label"], "path": f"/{slug}/"}
        for slug, page in MARKETING_PAGE_DEFINITIONS.items()
    ]


def _marketing_navbar_primary() -> list[dict]:
    """Public IA: six top links; Platform/Solutions/Resources use premium mega menu panels."""

    def p(name: str, fallback: str, **kwargs) -> str:
        u = _safe_reverse(name, kwargs=kwargs if kwargs else None)
        return u if u != "#" else fallback

    platform_path = p("marketing_platform", "/platform/")
    sis = p("marketing_platform_sis", "/platform/student-information-system/")
    admissions = p("marketing_platform_admissions", "/platform/admissions/")
    attendance = p("marketing_platform_attendance", "/platform/attendance/")
    fees = p("marketing_platform_fees_payments", "/platform/fees-payments/")
    grading = p(
        "marketing_platform_grading_report_cards",
        "/platform/grading-report-cards/",
    )
    parent_p = p("marketing_platform_parent_portal", "/platform/parent-portal/")
    teacher_p = p("marketing_platform_teacher_portal", "/platform/teacher-portal/")
    student_p = p("marketing_platform_student_portal", "/platform/student-portal/")
    comms = p("marketing_platform_communications", "/platform/communications/")
    analytics = p("marketing_platform_analytics", "/platform/analytics/")
    workflows = p("marketing_platform_workflows", "/platform/workflows/")
    offline = p("marketing_platform_offline_first", "/platform/offline-first/")
    security = p("marketing_platform_security", "/platform/security/")

    platform_mega_columns = [
        {
            "title": "Core operations",
            "links": [
                _nav_mega_link(
                    "Student Information System",
                    sis,
                    "Records, enrollment context, and learner profile continuity.",
                ),
                _nav_mega_link(
                    "Admissions",
                    admissions,
                    "Pipeline from enquiry through enrollment with one thread.",
                ),
                _nav_mega_link(
                    "Attendance & marks",
                    attendance,
                    "Daily presence and formative marks tied to the same learner record.",
                ),
                _nav_mega_link(
                    "Fees & payments",
                    fees,
                    "Invoices, receipts, and guardian visibility without spreadsheet drift.",
                ),
                _nav_mega_link(
                    "Grading & report cards",
                    grading,
                    "Assessment, transcripts, and reporting on one academic spine.",
                ),
            ],
        },
        {
            "title": "Portals",
            "links": [
                _nav_mega_link(
                    "Parent portal",
                    parent_p,
                    "Fees, announcements, and learner progress in one mobile-ready place.",
                ),
                _nav_mega_link(
                    "Teacher workspace",
                    teacher_p,
                    "Attendance, gradebook, and classroom workflows without tool sprawl.",
                ),
                _nav_mega_link(
                    "Student portal",
                    student_p,
                    "Assignments, schedules, and outcomes students can trust.",
                ),
                _nav_mega_link(
                    "Communications",
                    comms,
                    "Role-aware messaging that stays on the official channel.",
                ),
            ],
        },
        {
            "title": "Intelligence & control",
            "links": [
                _nav_mega_link(
                    "Analytics",
                    analytics,
                    "Leadership dashboards for enrollment, finance, and learning signals.",
                ),
                _nav_mega_link(
                    "Workflows",
                    workflows,
                    "Configurable approvals and handoffs without custom code.",
                ),
                _nav_mega_link(
                    "Offline-first",
                    offline,
                    "Classroom continuity when connectivity is unreliable.",
                ),
                _nav_mega_link(
                    "Security & governance",
                    security,
                    "Permissions, audit posture, and operator-grade boundaries.",
                ),
            ],
        },
    ]
    platform_children: list[dict] = [
        {"label": "Platform overview", "path": platform_path},
        *[dict(x) for col in platform_mega_columns for x in col["links"]],
    ]

    solutions_path = p("marketing_solutions", "/solutions/")
    priv = p("marketing_story_private_schools", "/for-private-schools/")
    intl = p("marketing_solutions_international_schools", "/solutions/international-schools/")
    k12 = p("marketing_solutions_k12_schools", "/solutions/k12-schools/")
    multi = p("marketing_solutions_multi_campus", "/solutions/multi-campus/")
    faith = p("marketing_solutions_faith_based_schools", "/solutions/faith-based-schools/")
    grow = p(
        "marketing_solutions_growing_school_networks",
        "/solutions/growing-school-networks/",
    )
    offline_story = p("marketing_story_offline_first", "/offline-first/")
    networks_story = p("marketing_story_school_networks", "/for-school-networks/")
    finance_role = p("role_finance", "/roles/finance/")
    teachers_role = p("role_teachers", "/roles/teachers/")
    parents_role = p("role_parents", "/roles/parents/")

    solutions_mega_columns = [
        {
            "title": "By school type",
            "links": [
                _nav_mega_link(
                    "Private schools",
                    priv,
                    "Enrollment velocity, parent trust, and fee clarity without chaos.",
                ),
                _nav_mega_link(
                    "International schools",
                    intl,
                    "Global families, flexible calendars, and multi-currency readiness.",
                ),
                _nav_mega_link(
                    "K–12 schools",
                    k12,
                    "Full learner lifecycle, divisions, and parent communication in sync.",
                ),
                _nav_mega_link(
                    "Multi-campus groups",
                    multi,
                    "Executive rollups, standards, and governance across campuses.",
                ),
                _nav_mega_link(
                    "Faith-based schools",
                    faith,
                    "Community trust, family communication, and mission-aligned operations.",
                ),
                _nav_mega_link(
                    "Growing school networks",
                    grow,
                    "Repeatable launch playbooks and shared configuration at scale.",
                ),
            ],
        },
        {
            "title": "Operating context & roles",
            "links": [
                _nav_mega_link(
                    "Solutions overview",
                    solutions_path,
                    "Map buyer journeys to the right proof points.",
                ),
                _nav_mega_link(
                    "Low-connectivity schools",
                    offline_story,
                    "Keep teaching and attendance moving when the network drops.",
                ),
                _nav_mega_link(
                    "School networks",
                    networks_story,
                    "How groups standardize without suffocating each campus.",
                ),
                _nav_mega_link(
                    "Finance teams",
                    finance_role,
                    "Billing, collections, and audit-friendly money workflows.",
                ),
                _nav_mega_link(
                    "Teachers & academics",
                    teachers_role,
                    "Classroom execution with less admin overhead.",
                ),
                _nav_mega_link(
                    "Parents & families",
                    parents_role,
                    "Guardian experience that feels intentional, not bolted on.",
                ),
            ],
        },
    ]
    solutions_children = [{"label": "Solutions overview", "path": solutions_path}]
    _sol_seen = {solutions_path}
    for col in solutions_mega_columns:
        for x in col["links"]:
            if x["path"] in _sol_seen:
                continue
            _sol_seen.add(x["path"])
            solutions_children.append({"label": x["label"], "path": x["path"]})

    resources_path = p("marketing_resources", "/resources/")
    tour = p("marketing_resources_product_tour", "/resources/product-tour/")
    guides = p("marketing_resources_guides", "/resources/guides/")
    cases = p("marketing_resources_case_studies", "/resources/case-studies/")
    help_c = p("marketing_resources_help_center", "/resources/help-center/")
    blog = p("marketing_resources_blog", "/resources/blog/")

    resources_mega_columns = [
        {
            "title": "Learn",
            "links": [
                _nav_mega_link(
                    "Resources hub",
                    resources_path,
                    "Curated entry points for buyers and operators.",
                ),
                _nav_mega_link(
                    "Product tour",
                    tour,
                    "Guided walkthrough of surfaces before you talk to sales.",
                ),
                _nav_mega_link(
                    "Guides",
                    guides,
                    "Deep dives on rollout, procurement, and operating model fit.",
                ),
                _nav_mega_link(
                    "Case studies",
                    cases,
                    "Structured stories—no fabricated logos or metrics.",
                ),
            ],
        },
        {
            "title": "Support & stories",
            "links": [
                _nav_mega_link(
                    "Help center",
                    help_c,
                    "Operational answers for teams rolling out RunMyCampus.",
                ),
                _nav_mega_link(
                    "Blog",
                    blog,
                    "Product, implementation, and platform craft notes.",
                ),
            ],
        },
    ]
    resources_children = [{"label": "Resources hub", "path": resources_path}]
    _res_seen = {resources_path}
    for col in resources_mega_columns:
        for x in col["links"]:
            if x["path"] in _res_seen:
                continue
            _res_seen.add(x["path"])
            resources_children.append({"label": x["label"], "path": x["path"]})

    why_path = p("marketing_10_reasons", "/10-reasons/")
    pricing_path = p("marketing_pricing", "/pricing/")
    trust_path = p("marketing_trust_dedicated", "/trust/")

    return [
        {
            "label": "Platform",
            "path": platform_path,
            "children": platform_children,
            "mega_columns": platform_mega_columns,
        },
        {
            "label": "Solutions",
            "path": solutions_path,
            "children": solutions_children,
            "mega_columns": solutions_mega_columns,
        },
        {"label": "Why RunMyCampus", "path": why_path},
        {"label": "Pricing", "path": pricing_path},
        {"label": "Trust", "path": trust_path},
        {
            "label": "Resources",
            "path": resources_path,
            "children": resources_children,
            "mega_columns": resources_mega_columns,
        },
    ]



def _topical_nav() -> list[dict]:
    return [
        {"slug": slug, "label": topic["label"], "path": f"/solutions/{slug}/"}
        for slug, topic in TOPICAL_LANDING_DEFINITIONS.items()
    ]


# Buyer-facing order: ERP/admissions/parents first; fills to `limit` from the full registry.
_TOPICAL_NAV_FEATURED_SLUGS: tuple[str, ...] = (
    "school-erp",
    "admissions-software",
    "parent-app",
    "k12-school-management-system",
    "multi-campus-school-software",
    "student-passport-transcript-portability",
)


def _topical_nav_featured(limit: int = 4) -> list[dict]:
    """Curated subset for marketing footers and inner tails—avoids a wall of topic links."""
    items: list[dict] = []
    seen: set[str] = set()
    for slug in _TOPICAL_NAV_FEATURED_SLUGS:
        topic = TOPICAL_LANDING_DEFINITIONS.get(slug)
        if not topic or slug in seen:
            continue
        items.append({"slug": slug, "label": topic["label"], "path": f"/solutions/{slug}/"})
        seen.add(slug)
        if len(items) >= limit:
            return items
    for slug, topic in TOPICAL_LANDING_DEFINITIONS.items():
        if slug in seen:
            continue
        items.append({"slug": slug, "label": topic["label"], "path": f"/solutions/{slug}/"})
        seen.add(slug)
        if len(items) >= limit:
            break
    return items


def _get_country_from_request(request) -> str:
    """Country code (alpha-2) from GeoIP for marketing personalization."""
    try:
        from apps.compliance.access_control import get_country_from_ip

        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[
            0
        ].strip() or request.META.get("REMOTE_ADDR", "")
        if not ip:
            return ""
        code = (get_country_from_ip(ip) or "").strip().upper()[:2]
        return code
    except (ImportError, AttributeError, TypeError, ValueError, OSError):
        return ""


def _normalize_country_code(value: str) -> str:
    alpha3 = GlobalGeoCatalog.normalize_country_code(value)
    alpha2 = GlobalGeoCatalog.alpha2_for_country(alpha3)
    if alpha2:
        return alpha2.upper()
    raw = (value or "").strip().upper()[:2]
    return raw


def _normalize_language_code(value: str, fallback: str = "en") -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return fallback
    # Keep language only; regional variants are folded for route stability.
    return raw.split("-", 1)[0]


def _absolute_url(request, path: str) -> str:
    scheme = "https" if request.is_secure() else "http"
    host = (request.get_host() or "").split(":")[0]
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{scheme}://{host}{path}"


def _global_hreflang_entries(
    request, *, country_code: str, language_code: str
) -> list[dict]:
    _language = _normalize_language_code(language_code or "en")
    country = _normalize_country_code(country_code)
    if not country:
        return []
    entries = []
    supported = ["en", "fr", "pt", "ar"]
    for item in supported:
        path = f"/{item}/{country.lower()}/"
        entries.append(
            {"hreflang": f"{item}-{country}", "href": _absolute_url(request, path)}
        )
    entries.append({"hreflang": "x-default", "href": _absolute_url(request, "/")})
    return entries


def _host_url(request, host: str, path: str = "/") -> str:
    if not host:
        return "#"
    scheme = "https" if request.is_secure() else "http"
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{scheme}://{host}{normalized_path}"


def _get_regional_pitch(country_code: str, language_code: str) -> dict:
    """
    Merge RegionalPitch overrides over GlobalBrandRegistry defaults.
    """
    brand = resolve_global_brand_context(
        country_code=country_code, language_code=language_code
    )
    seo = brand.get("seo_config") or {}
    default = {
        "headline": seo.get("headline") or "RunMyCampus",
        "subheadline": seo.get("subheadline")
        or "Global school operations, localized for every campus.",
        "features": seo.get("features") or [],
        "visual_variant": seo.get("visual_variant") or "",
        "seo_title": seo.get("seo_title") or "RunMyCampus | Global School Operating Platform",
        "seo_description": seo.get("seo_description")
        or (
            "RunMyCampus connects admissions, student records, attendance, grading, fees, "
            "communication, reporting, and school operations in one platform built for schools worldwide."
        ),
    }

    country = _normalize_country_code(country_code)
    if not country:
        return default

    try:
        from apps.siteconfig.models import RegionalPitch

        pitch = RegionalPitch.objects.filter(
            country_code=country, is_active=True
        ).first()
    except (ImportError, DatabaseError, OperationalError, AttributeError, TypeError):
        pitch = None
    if not pitch:
        return default

    return {
        "headline": pitch.headline or default["headline"],
        "subheadline": pitch.subheadline or default["subheadline"],
        "features": pitch.features or default["features"],
        "visual_variant": pitch.visual_variant or default["visual_variant"],
        "seo_title": pitch.seo_title or default["seo_title"],
        "seo_description": pitch.seo_description or default["seo_description"],
    }


def _geo_copy_variations(country: str) -> dict:
    """Evidence-driven copy variations by geo cluster (Wave 4). Use in templates for CTA/headline by region."""
    variants = {
        "CM": {
            "cta_primary": "Réserver une démo",
            "proof_lead": "Conçu pour les écoles francophones et les équipes qui opèrent à l'international.",
        },
        "CA": {
            "cta_primary": "Book a demo",
            "proof_lead": "Built for Canadian schools and multi-province deployments.",
        },
        "NG": {
            "cta_primary": "Book a demo",
            "proof_lead": "Designed for Nigerian schools and WAEC alignment.",
        },
        "GB": {
            "cta_primary": "Book a demo",
            "proof_lead": "UK term structures and British curriculum support.",
        },
    }
    return variants.get(
        country,
        {
            "cta_primary": "Book a demo",
            "proof_lead": "One platform for admissions, academics, and operations.",
        },
    )


def _tenant_example_slug_for_marketing() -> str | None:
    """
    Return a tenant slug suitable for marketing (e.g. regional landing).
    Prefer a non-excluded slug so links do not send users to school-not-found.
    """
    import os
    from django.conf import settings
    from apps.schools.models import School

    slug = getattr(settings, "TENANT_EXAMPLE_SLUG", None) or None
    if slug:
        return str(slug).strip().lower() or None
    excluded = {
        item.strip().lower()
        for item in (os.getenv("MARKETING_EXCLUDED_TENANT_SLUGS") or "").split(",")
        if item.strip()
    }
    school = School.objects.filter(is_active=True).order_by("created_at")
    if excluded:
        school = school.exclude(slug__in=excluded).exclude(subdomain__in=excluded)
    return school.values_list("slug", flat=True).first()


def _marketing_context(
    request, *, country_code: str, language_code: str, regional: bool
) -> dict:
    country = _normalize_country_code(country_code)
    brand = resolve_global_brand_context(
        country_code=country, language_code=language_code
    )
    language = _normalize_language_code(
        language_code, fallback=brand.get("primary_language") or "en"
    )
    pitch = _get_regional_pitch(country, language)
    if regional and not country:
        raise Http404("Region not found")

    canonical_path = "/" if not regional else f"/{language}/{country.lower()}/"
    canonical_url = _absolute_url(request, canonical_path)
    hreflang_entries = _global_hreflang_entries(
        request, country_code=country, language_code=language
    )
    canonical_domain = get_canonical_base_domain()
    country_label = brand.get("country_name") or "Global"
    tenant_example_slug = _tenant_example_slug_for_marketing()
    tenant_login_path = "/authentication/login/"
    public_host = canonical_domain
    manager_host = f"manager.{canonical_domain}"
    api_host = f"api.{canonical_domain}"
    docs_host = f"docs.{canonical_domain}"
    tenant_host = (
        f"{tenant_example_slug}.{canonical_domain}"
        if tenant_example_slug
        else f"your-school.{canonical_domain}"
    )

    # School Identity card: link to tenant login only if we have a real example; else link to find school
    school_identity_primary_url = (
        _host_url(request, tenant_host, tenant_login_path)
        if tenant_example_slug
        else request.build_absolute_uri(_safe_reverse("find_school"))
    )
    school_identity_primary_label = (
        "Tenant login" if tenant_example_slug else "Find your school"
    )

    surface_cards = [
        {
            "name": "Global Authority",
            "host": public_host,
            "headline": "Public growth engine",
            "summary": "SEO-ready landing pages, localized proof blocks, and guided conversion flows for school operators.",
            "primary_cta_label": "Explore platform",
            "primary_cta_path": "/product/",
            "secondary_cta_label": "Find your school",
            "secondary_cta_path": _safe_reverse("global_login_discovery"),
        },
        {
            "name": "School Identity",
            "host": tenant_host,
            "headline": "White-label tenant access",
            "summary": "Tenant entry is branded with school identity while preserving strict subdomain isolation for security.",
            "primary_cta_label": school_identity_primary_label,
            "primary_cta_url": school_identity_primary_url,
            "secondary_cta_label": "School finder",
            "secondary_cta_path": _safe_reverse("find_school"),
        },
        {
            "name": "Manager Operations",
            "host": manager_host,
            "headline": "Command center for operators",
            "summary": "Global support, provisioning, and governance workflows run from a dedicated manager host.",
            "primary_cta_label": "Manager login",
            "primary_cta_url": _host_url(request, manager_host, tenant_login_path),
            "secondary_cta_label": "Architecture compare",
            "secondary_cta_path": "/compare/",
        },
    ]

    authority_metrics = [
        {
            "label": "Country Profile",
            "value": country_label,
            "detail": "Resolved from global brand registry.",
        },
        {
            "label": "Canonical Domain",
            "value": canonical_domain,
            "detail": "Public, tenant, and manager host contract.",
        },
        {
            "label": "API Surface",
            "value": api_host,
            "detail": "Integration-first architecture and governance.",
        },
        {
            "label": "Docs Surface",
            "value": docs_host,
            "detail": "Canonical implementation and onboarding guides.",
        },
    ]

    proof_points = [
        {
            "title": "Security-first tenancy",
            "body": "Every school is isolated on subdomain boundaries to protect sessions, policies, and data context.",
        },
        {
            "title": "Registry-driven localization",
            "body": f"Terminology, formatting, and compliance defaults adapt for {country_label} without branching code per tenant.",
        },
        {
            "title": "Operator observability",
            "body": "Support and manager workflows stay auditable across discovery, onboarding, and tenant operations.",
        },
    ]

    trust_badges = [
        "Built for schools worldwide",
        "Flexible academic calendars",
        "Multi-currency fee structures",
        "Role-based portals",
        "Offline-ready workflows",
        "Secure audit trails",
        "Multi-campus support",
    ]

    rollout_steps = [
        {
            "step": "1",
            "title": "Acquire and convert",
            "body": "Drive acquisition from marketing pages with country/language messaging and clear conversion CTAs.",
        },
        {
            "step": "2",
            "title": "Locate the right school",
            "body": "Use school finder and discovery routes to route users to the exact tenant subdomain.",
        },
        {
            "step": "3",
            "title": "Operate at scale",
            "body": "Support and manager teams run governance, provisioning, and audit workflows from dedicated hosts.",
        },
    ]
    audience_segments = [
        {
            "name": "Single-campus schools",
            "summary": "Launch admissions, academics, billing, and parent communication from one operating console.",
            "cta_label": "See onboarding flow",
            "cta_path": _safe_reverse("signup_school"),
        },
        {
            "name": "School groups and chains",
            "summary": "Run multi-campus standards with local campus autonomy, branding, and policy controls.",
            "cta_label": "Compare architecture",
            "cta_path": "/compare/",
        },
        {
            "name": "Regional operators",
            "summary": "Scale language, terminology, and compliance defaults across country-specific deployments.",
            "cta_label": "Explore localized pages",
            "cta_path": "/solutions/",
        },
    ]

    proof_stats = [
        {
            "value": "1",
            "label": "connected record thread",
            "detail": "Admissions, roster, billing, and academics reference the same student context.",
        },
        {
            "value": "Multi",
            "label": "calendars & grading models",
            "detail": "Terms, scales, departments, and structures configurable per institution.",
        },
        {
            "value": "Audited",
            "label": "governance posture",
            "detail": "Role-based access, approvals, and operator-visible audit trails.",
        },
        {
            "value": "Offline-ready",
            "label": "capture paths",
            "detail": "Queue attendance, marks, and receipts when connectivity is unreliable.",
        },
    ]
    institution_logos: list[str] = []

    admissions_flow = [
        {
            "title": "Capture enquiries",
            "body": "Collect parent leads with campaign-aware forms and route follow-up ownership by school.",
        },
        {
            "title": "Qualify and schedule",
            "body": "Track counselor interactions, interview status, and required documents in one flow.",
        },
        {
            "title": "Convert and onboard",
            "body": "Move accepted applicants into tenant enrollment and activate role-ready access.",
        },
    ]

    pricing_snapshot = [
        {
            "plan": "Starter",
            "tagline": "Schools digitizing core records, attendance, communications, and simple reporting.",
            "highlights": [
                "Student Information System essentials",
                "Attendance & timetable basics",
                "Parent / teacher / student portal entry points",
                "Standard support",
            ],
            "cta_label": "Book demo",
            "cta_path": _safe_reverse("marketing_demo") or "/demo/",
        },
        {
            "plan": "Growth",
            "tagline": "Schools running admissions, fees, grading, engagement, and daily operations.",
            "highlights": [
                "Full admissions & enrollment workflows",
                "Fees, invoices, and payment discipline",
                "Grading, exams, and published report cards",
                "Analytics for leadership reviews",
            ],
            "cta_label": "See pricing details",
            "cta_path": "/pricing/",
        },
        {
            "plan": "Enterprise",
            "tagline": "Groups and advanced institutions needing multi-campus governance and depth.",
            "highlights": [
                "Multi-campus controls & custom workflows",
                "Offline sync & integration-ready APIs",
                "Advanced analytics & audit-heavy governance",
                "Priority implementation support",
            ],
            "cta_label": "Book demo",
            "cta_path": "/demo/",
        },
    ]

    trust_controls = [
        "FERPA- and GDPR-conscious workflows",
        "Audit trails for support and admin actions",
        "Role-based access and approval controls",
        "Regional compliance defaults per country profile",
        "Cross-subdomain CSRF and session guardrails",
        "Host-level routing contract enforcement",
    ]

    # Plan 4.11 / MARKETING_PAGE_AUDIT: explicit "what you get" trio on landing (not only long compliance list).
    what_you_get = [
        {
            "title": "Data security",
            "body": (
                "Encryption in transit and at rest, regional defaults, and audit trails "
                "aligned with FERPA and GDPR practices."
            ),
        },
        {
            "title": "Implementation support",
            "body": (
                "Named onboarding paths and escalation during rollout—scoped to what your "
                "contract includes."
            ),
        },
        {
            "title": "Customizable branding",
            "body": (
                "White-label surfaces, theme packs, and per-tenant visuals without "
                "splitting your data model."
            ),
        },
    ]

    # Plan 4.11: Post-enrollment revenue section (Events, Online Courses, Alumni)
    post_enrollment_revenue = [
        {
            "title": "School Events",
            "body": "Event ticketing, venue management, and sponsor engagement for school fundraisers and activities.",
        },
        {
            "title": "Online Courses",
            "body": "Course creation, student tracking, and certification for revenue and extended learning.",
        },
        {
            "title": "Alumni Network",
            "body": "Mentorship programs, fundraising campaigns, and career services for alumni relations.",
        },
    ]

    # Plan 4.11: explicit "Global features" list for hero (full list from plan)
    global_features = [
        "Multi-Language",
        "Multi-Currency",
        "Timezone-aware",
        "Country-Specific Grading",
        "Localized Holiday Calendars",
        "Data Residency",
        "AI-Powered Insights",
        "Customizable Workflows",
        "Scalable architecture",
        "Rollout support options",
    ]

    structured_data = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "RunMyCampus",
        "applicationCategory": "EducationalApplication",
        "operatingSystem": "Web",
        "url": canonical_url,
        "description": pitch.get("seo_description"),
        "areaServed": brand.get("country_name") or "Global",
    }
    canonical_base_url = request.build_absolute_uri("/")
    organization_schema_json = json.dumps(_organization_schema(canonical_base_url))

    # A/B testing: persist variant in session for hero/CTA (Plan 4.11)
    hero_variant = request.session.get("marketing_ab_variant")
    if not hero_variant:
        hero_variant = random.choice(["A", "B"])
        request.session["marketing_ab_variant"] = hero_variant
    marketing_cta_variant = request.session.get("marketing_cta_variant") or ""
    if not marketing_cta_variant:
        marketing_cta_variant = random.choice(["default", "secondary"])
        request.session["marketing_cta_variant"] = marketing_cta_variant

    demo_tenant_url = getattr(settings, "MARKETING_DEMO_TENANT_URL", "") or ""
    marketing_analytics_script_url = (
        getattr(settings, "MARKETING_ANALYTICS_SCRIPT_URL", "") or ""
    )
    marketing_analytics_endpoint_url = (
        getattr(settings, "MARKETING_ANALYTICS_ENDPOINT_URL", "") or ""
    )
    marketing_analytics_preconnect_origin = ""
    if marketing_analytics_script_url:
        try:
            parsed = urlparse(marketing_analytics_script_url)
            if parsed.scheme and parsed.netloc:
                marketing_analytics_preconnect_origin = (
                    f"{parsed.scheme}://{parsed.netloc}"
                )
        except (ValueError, TypeError, AttributeError):
            pass

    # Homepage promise: global SaaS OS story; CMS / geo / channel may override below.
    hero_headline = "Offline-ready education operating system for modern schools."
    hero_subheadline = (
        "One truthful picture of enrollment, fees, and learner progress across admissions, "
        "academics, finance, communication, reporting, and daily school operations."
    )
    _hero_by_country: dict[str, dict[str, str]] = {}
    _hero_by_channel = {
        "google": {
            "headline": "Offline-ready education operating system for modern schools.",
            "subheadline": (
                "Unify attendance, marks, fees, parent comms, and operations—book a walkthrough "
                "to see how it fits your campuses."
            ),
        },
        "linkedin": {
            "headline": "School operations, unified.",
            "subheadline": (
                "For education leaders: one guided command center for academics, finance, and "
                "family experience—without tool sprawl."
            ),
        },
        "facebook": {
            "headline": "Run your school on one platform.",
            "subheadline": (
                "Admissions through daily operations in one place—see the product tour or book a demo."
            ),
        },
        "newsletter": {
            "headline": "Offline-ready education operating system for modern schools.",
            "subheadline": (
                "For subscribers: how schools run attendance, fees, reports, and parent comms "
                "from one governed stack."
            ),
        },
    }
    if country in _hero_by_country:
        hero_headline = _hero_by_country[country].get("headline", hero_headline)
        hero_subheadline = _hero_by_country[country].get(
            "subheadline", hero_subheadline
        )
    utm_source = (request.GET.get("utm_source") or "").strip().lower()
    if utm_source in _hero_by_channel:
        hero_headline = _hero_by_channel[utm_source].get("headline", hero_headline)
        hero_subheadline = _hero_by_channel[utm_source].get(
            "subheadline", hero_subheadline
        )
    _book_demo = _safe_reverse("marketing_demo") or "/demo/"
    _product_tour = (
        _safe_reverse("marketing_resources_product_tour") or "/resources/product-tour/"
    )
    hero_ctas = [
        {"label": "Book demo", "url": _book_demo, "primary": True},
        {"label": "See product tour", "url": _product_tour, "primary": False},
    ]
    trust_logos: list[dict[str, str]] = []
    # Module screenshot paths relative to static root (SVG placeholders included; replace with PNGs if desired)
    core_modules = [
        {
            "title": "Admissions & Enrollment",
            "summary": "Capture leads, track applications, and onboard students in one flow.",
            "screenshot_url": "images/marketing/module-admissions.svg",
        },
        {
            "title": "Academics & Grades",
            "summary": "Syllabi, attendance, report cards, and interventions in a single source of truth.",
            "screenshot_url": "images/marketing/module-academics.svg",
        },
        {
            "title": "Finance & Billing",
            "summary": "Fees, payments, and financial reporting tailored to your school model.",
            "screenshot_url": "images/marketing/module-finance.svg",
        },
        {
            "title": "Communication",
            "summary": "Parents, teachers, and students stay connected with role-ready portals.",
            "screenshot_url": "images/marketing/module-communication.svg",
        },
        {
            "title": "Compliance & Reporting",
            "summary": "Audit trails, regional compliance defaults, and export-ready reports.",
            "screenshot_url": "images/marketing/module-compliance.svg",
        },
    ]
    platform_cards = [
        {
            "title": "Workflows that adapt",
            "summary": "From enquiry to graduation, every step is configurable to your school's processes and policies.",
        },
        {
            "title": "Dashboards that inform",
            "summary": "Leaders get real-time visibility into enrollment, attendance, and outcomes without switching tools.",
        },
        {
            "title": "Marketplace that extends",
            "summary": "Add integrations and apps from the marketplace without leaving the platform.",
        },
    ]
    # O17: "Scales globally" (WHAT_IS_LEFT_MASTER)
    scales_globally_line = (
        "Configurable calendars, grading scales, currencies, languages, and portals for international schools."
    )
    three_key_features = [
        "Unified admissions → roster → billing thread",
        "Role-ready portals for every stakeholder",
        "Offline-capable capture when networks struggle",
    ]
    migration_bullets = [
        "Import students, staff, and historical data from spreadsheets or legacy systems.",
        "Map your existing workflows to RunMyCampus modules with guided setup.",
        "Global-ready configuration: " + scales_globally_line,
        "Go live with phased rollout and implementation support.",
    ]
    # Migration visual: required; never leave section empty (per Visual Asset plan). Ultra high-end: dedicated migration-flow.svg.
    migration_studio_image_url = (
        getattr(settings, "MARKETING_MIGRATION_STUDIO_IMAGE_URL", None)
        or getattr(settings, "MARKETING_MIGRATION_CLOUD_DIAGRAM_URL", None)
        or static("images/marketing/migration-flow.svg")
    )
    # 7.1: Prefer AI-generated / governed assets from marketing_ai when set
    from apps.schools.marketing_ai import get_marketing_ai_asset_url

    hero_dashboard_image_url = (
        get_marketing_ai_asset_url("hero_dashboard")
        or getattr(settings, "MARKETING_HERO_IMAGE_URL", None)
        or ""
    )
    if not hero_dashboard_image_url:
        hero_dashboard_image_url = static(
            "images/marketing/hero-global-os-composite.svg"
        )
    # 9.5 proof-rich marketing: key for asset governance (style guide, versioning, approval).
    proof_hero_image_key = (
        getattr(settings, "MARKETING_PROOF_HERO_IMAGE_KEY", None) or "hero_dashboard"
    )
    _ai_video = get_marketing_ai_asset_url("hero_video")
    _settings_video = getattr(settings, "MARKETING_HERO_VIDEO_URL", None)
    if _ai_video:
        hero_video_url = _ai_video
    elif _settings_video is not None:
        hero_video_url = (_settings_video or "").strip()
    else:
        hero_video_url = ""
    hero_video_poster_url = (
        getattr(settings, "MARKETING_HERO_VIDEO_POSTER_URL", None)
        or hero_dashboard_image_url
        or ""
    )
    product_demo_image_url = (
        getattr(settings, "MARKETING_PRODUCT_DEMO_IMAGE_URL", None)
        or getattr(settings, "MARKETING_HERO_IMAGE_URL", None)
        or hero_dashboard_image_url
        or static("images/marketing/hero-global-os-composite.svg")
    )
    # Product visualization strip: 5 slides required (Batch 1 — admin, teacher, parent, student, analytics).
    # Proof-rich §8.4: every slide has non-empty image_static when image_url missing so section never shows empty frames.
    _proof_viz_fallback = "images/marketing/platform-diagram-marketing.svg"
    product_visualization_slides = getattr(
        settings, "MARKETING_PRODUCT_VISUALIZATION_SLIDES", None
    ) or [
        {
            "title": "School command center",
            "caption": "Enrollment, finance, and operational signals for leadership.",
            "image_url": "",
            "image_static": "images/marketing/viz-admin.svg",
        },
        {
            "title": "Teacher workspace",
            "caption": "Attendance, marks, and class context without tab sprawl.",
            "image_url": "",
            "image_static": "images/marketing/viz-teacher.svg",
        },
        {
            "title": "Family home",
            "caption": "Fees, attendance, announcements, and messaging families can trust.",
            "image_url": "",
            "image_static": "images/marketing/module-communication.svg",
        },
        {
            "title": "Payment readiness",
            "caption": "Honest view of rails, configuration, and reconciliation—not hype.",
            "image_url": "",
            "image_static": "images/marketing/module-finance.svg",
        },
        {
            "title": "Offline sync",
            "caption": "Capture-first flows with queues you can review after reconnect.",
            "image_url": "",
            "image_static": "images/marketing/setup-studio-flow.svg",
        },
        {
            "title": "Next action",
            "caption": "What to clear next—approvals, exceptions, and follow-ups surfaced.",
            "image_url": "",
            "image_static": "images/marketing/health-score-visual.svg",
        },
    ]
    for slide in product_visualization_slides:
        if not slide.get("image_url") and not slide.get("image_static"):
            slide["image_static"] = _proof_viz_fallback
    _marketplace_path = (
        _safe_reverse("marketing_app_marketplace") or "/app-marketplace/"
    )
    _integrations_path = _safe_reverse("marketing_integrations") or "/integrations/"
    ecosystem_apps = [
        {
            "name": "LMS / LTI",
            "summary": "Connect your learning management system.",
            "image_url": "",
            "install_path": _marketplace_path,
            "cta_path": _marketplace_path,
            "cta_label": "Explore",
        },
        {
            "name": "Payment gateways",
            "summary": (
                "Connect gateways and local rails your deployment supports; availability depends "
                "on region and configuration—see payment readiness for an honest view."
            ),
            "image_url": "",
            "install_path": _integrations_path,
            "cta_path": _integrations_path,
            "cta_label": "View integrations",
        },
        {
            "name": "Messaging",
            "summary": "SMS and email providers for notifications.",
            "image_url": "",
            "install_path": _integrations_path,
            "cta_path": _integrations_path,
            "cta_label": "View integrations",
        },
        {
            "name": "Single sign-on",
            "summary": "SAML and OAuth for enterprise identity.",
            "image_url": "",
            "install_path": _integrations_path,
            "cta_path": _integrations_path,
            "cta_label": "View integrations",
        },
    ]
    testimonials: list[dict[str, object]] = []
    _video_testimonials_setting = getattr(
        settings, "MARKETING_VIDEO_TESTIMONIALS", None
    )
    video_testimonials = _video_testimonials_setting or []
    security_badges = [
        "FERPA-conscious workflows",
        "GDPR-aligned practices",
        "Encryption at rest & in transit",
        "Role-based access",
        "Per-tenant isolation",
    ]
    final_cta_headline = "See RunMyCampus on your terms."

    # Homepage strip: same buyer segments as primary Solutions nav (not a parallel catalog).
    institution_types = [
        {
            "label": "Private schools",
            "summary": "Admissions depth, branded portals, and fee clarity families trust.",
            "path": _safe_reverse("marketing_story_private_schools") or "/for-private-schools/",
        },
        {
            "label": "School networks",
            "summary": "Standards, visibility, and rollout without smothering each campus.",
            "path": _safe_reverse("marketing_story_school_networks") or "/for-school-networks/",
        },
        {
            "label": "Low-connectivity schools",
            "summary": "Offline-first capture and sync you can reconcile when links return.",
            "path": _safe_reverse("marketing_story_offline_first") or "/offline-first/",
        },
        {
            "label": "Finance teams",
            "summary": "Invoices, receipts, arrears, and leadership-ready fee posture.",
            "path": _safe_reverse("role_finance") or "/roles/finance/",
        },
        {
            "label": "Teachers & academics",
            "summary": "Attendance, marks, and parent messaging without tool sprawl.",
            "path": _safe_reverse("role_teachers") or "/roles/teachers/",
        },
        {
            "label": "Parents & families",
            "summary": "One portal for fees, attendance, announcements, and report cards.",
            "path": _safe_reverse("role_parents") or "/roles/parents/",
        },
    ]

    # Phase 2: Workflow automation (section 4)
    workflow_automation = [
        {
            "title": "Enquiry to enrollment",
            "body": "Capture leads, qualify applicants, and onboard students in one configurable flow.",
        },
        {
            "title": "Grades and attendance",
            "body": "Syllabi, report cards, and interventions with role-ready dashboards for teachers and admins.",
        },
        {
            "title": "Fees and payments",
            "body": (
                "Billing cycles and financial reporting without spreadsheets—gateway availability "
                "depends on region and deployment (see payment readiness)."
            ),
        },
        {
            "title": "Approvals and audits",
            "body": "Configurable approval chains and audit trails for compliance and governance.",
        },
    ]

    # Phase 2: Developer platform (section 8) – one card for landing
    developer_platform_card = {
        "title": "Developer platform",
        "summary": "APIs, webhooks, and SDKs to integrate RunMyCampus with your LMS, SIS, and internal tools.",
        "cta_label": "Developer docs",
        "cta_path": _safe_reverse("marketing_developers") or "/developers/",
    }

    category_claim = (
        "One story: calmer operations, clearer families, and honest payment posture."
    )
    platform_pillar_grid = [
        {
            "label": "Command center",
            "sub": "Run every campus from one guided operating layer.",
        },
        {
            "label": "Operator visibility",
            "sub": "See schools, risk signals, and the next best action.",
        },
        {
            "label": "Trackable school events",
            "sub": "Important actions leave an audit-friendly trail.",
        },
        {
            "label": "Workflow automation",
            "sub": "Automate reminders, follow-ups, and approvals without shadow processes.",
        },
        {
            "label": "Offline queue",
            "sub": "Keep teaching and fee capture moving when connectivity drops.",
        },
        {
            "label": "Global payments",
            "sub": "Local rails where enabled—with transparent gaps on the readiness page.",
        },
    ]
    from_single_to_enterprise = [
        {
            "stage": "Single school",
            "summary": "One campus, one tenant. Launch in days.",
        },
        {
            "stage": "Network",
            "summary": "Multi-campus with central oversight and campus autonomy.",
        },
        {
            "stage": "White-label operator",
            "summary": "National scale with dedicated manager operations and branding.",
        },
    ]

    by_the_numbers: list[dict[str, str]] = []
    outcome_metrics = getattr(settings, "MARKETING_OUTCOME_METRICS", None) or []
    customer_logos: list[dict[str, str]] = []
    awards_recognition: list[str] = []
    review_badges: list[dict[str, str]] = []
    ten_reasons_page_path = _safe_reverse("marketing_10_reasons") or "/10-reasons/"

    # Non-negotiables: discovery (role + challenge)
    for_your_role = [
        {
            "label": "Owners",
            "path": _safe_reverse("role_principals") or "/roles/principals/",
            "summary": "Enrollment, revenue, risk, and multi-campus posture without spreadsheet drift.",
        },
        {
            "label": "Administrators",
            "path": _safe_reverse("role_school_admin") or "/roles/school-admin/",
            "summary": "Admissions, records, reporting, communications, and daily operations.",
        },
        {
            "label": "Teachers",
            "path": _safe_reverse("role_teachers") or "/roles/teachers/",
            "summary": "Attendance, marks, assignments, and family messaging in one workspace.",
        },
        {
            "label": "Parents",
            "path": _safe_reverse("role_parents") or "/roles/parents/",
            "summary": "Fees, attendance, announcements, results, and report cards in one portal.",
        },
        {
            "label": "Finance teams",
            "path": _safe_reverse("role_finance") or "/roles/finance/",
            "summary": "Invoices, receipts, balances, discounts, arrears, and finance reporting.",
        },
        {
            "label": "School networks",
            "path": _safe_reverse("marketing_story_school_networks") or "/for-school-networks/",
            "summary": "Repeatable launch kits, standards, and visibility across campuses.",
        },
    ]
    _offline_story = _safe_reverse("marketing_story_offline_first") or "/offline-first/"
    _payments_story = (
        _safe_reverse("marketing_story_payments_readiness") or "/payments-readiness/"
    )
    solve_by_challenge = [
        {
            "title": "Internet outages",
            "path": _offline_story,
        },
        {
            "title": "Fee collection",
            "path": _payments_story,
        },
        {
            "title": "Report cards",
            "path": _safe_reverse("marketing_platform_grading_report_cards")
            or "/platform/grading-report-cards/",
        },
        {
            "title": "Parent communication",
            "path": _safe_reverse("marketing_platform_communications")
            or "/platform/communications/",
        },
        {
            "title": "Teacher workload",
            "path": _safe_reverse("role_teachers") or "/roles/teachers/",
        },
        {
            "title": "Admin visibility",
            "path": _safe_reverse("role_school_admin") or "/roles/school-admin/",
        },
    ]

    # Non-negotiables: ecosystem
    app_marketplace_hero = {
        "title": "App Marketplace",
        "summary": "Extend RunMyCampus with integrations and apps. Connect your LMS, payments, messaging, and identity providers.",
        "app_count": "50+",
        "cta_path": _safe_reverse("marketing_app_marketplace") or "/app-marketplace/",
        "cta_label": "View App Marketplace",
    }
    developer_story_summary = "By developers, for developers. APIs, webhooks, and SDKs let you build apps and integrations that schools install. Create custom storefronts and extend the platform."
    partners_list = [
        {
            "name": "Integrations catalog",
            "url": _safe_reverse("marketing_integrations") or "/integrations/",
        },
        {
            "name": "Developer program",
            "url": _safe_reverse("marketing_developers") or "/developers/",
        },
    ]
    integrations_strip = [
        "Clever",
        "Google Classroom",
        "Stripe",
        "PayPal",
        "SAML",
        "OAuth",
    ]

    # Non-negotiables: thought leadership
    gated_report_cta = {
        "headline": "Download the State of School Operations report",
        "url": _safe_reverse("marketing_resources") or "/resources/",
        "cta_label": "Get the report",
    }
    second_lead_magnet = {
        "title": "Implementation checklist",
        "summary": "Step-by-step checklist to go live with RunMyCampus.",
        "url": _safe_reverse(
            "marketing_buyer_toolkit_download",
            kwargs={"document": "implementation-checklist"},
        )
        or "/buyer-toolkit/download/implementation-checklist/",
    }
    resources_hub_path = _safe_reverse("marketing_resources") or "/resources/"

    # Non-negotiables: events & community
    events_list = [
        {
            "title": "Customer roundtable: Migration in 90 days",
            "date": "Monthly",
            "cta_url": _safe_reverse("marketing_events") or "/events/",
            "cta_label": "Register",
        },
    ]
    flagship_event = {
        "name": "RunMyCampus Live",
        "summary": "Annual education operations summit. Be first to know when we announce dates.",
        "cta_url": _safe_reverse("marketing_events") or "/events/",
        "cta_label": "Be first to know",
    }
    community_cta = {
        "label": "Join our newsletter",
        "url": _safe_reverse("marketing_contact") or "/contact/",
        "summary": "Get product updates and best practices.",
    }

    # Non-negotiables: trust & support
    support_implementation_copy = "We set you up. Dedicated onboarding and support when you need it—so you're not just buying software, you're getting a partner for go-live."
    accessibility_line = "Accessible by design. We align with inclusive design practices and regional accessibility requirements."
    why_switch_path = _safe_reverse("marketing_why_switch") or "/why-switch/"
    # Explicit "Why switch now" messaging (homepage narrative)
    why_switch_bullets = [
        "Replace legacy SIS pain with one modern platform.",
        "Easier onboarding: Setup Studio gets you live in days, not months.",
        "Better family experience: one portal for attendance, grades, and payments.",
        "Stronger district governance: control plane for multi-school operators.",
        "Safer migration: mapping, validation, and rollback before go-live.",
        "Richer extensibility: marketplace, blueprints, and workflow packs.",
        "Lower-click workflows: command palette and role-native homes.",
    ]

    # Non-negotiables: 3-step get started
    get_started_three_steps = [
        {
            "step": 1,
            "title": "Sign up",
            "body": "Start your free trial—no credit card required.",
        },
        {
            "step": 2,
            "title": "Add your school",
            "body": "Configure your tenant, terms, and branding.",
        },
        {
            "step": 3,
            "title": "Invite your team",
            "body": "Invite admins, teachers, and parents. Go live.",
        },
    ]

    product_pillars_home = [
        {
            "title": "Student Information System",
            "summary": "Holistic records across guardians, academics, and finance.",
            "path": _safe_reverse("marketing_platform_sis")
            or "/platform/student-information-system/",
            "screenshot_static": "images/marketing/viz-student360.svg",
        },
        {
            "title": "Admissions & Enrollment",
            "summary": "Inquiry through enrollment with governed pipelines.",
            "path": _safe_reverse("marketing_platform_admissions")
            or "/platform/admissions/",
            "screenshot_static": "images/marketing/module-admissions.svg",
        },
        {
            "title": "Attendance & Timetable",
            "summary": "Daily registers aligned to calendars—online or offline-first.",
            "path": _safe_reverse("marketing_platform_attendance")
            or "/platform/attendance/",
            "screenshot_static": "images/marketing/module-academics.svg",
        },
        {
            "title": "Fees, Invoices & Payments",
            "summary": "Multi-currency structures with guardian-visible balances.",
            "path": _safe_reverse("marketing_platform_fees_payments")
            or "/platform/fees-payments/",
            "screenshot_static": "images/marketing/module-finance.svg",
        },
        {
            "title": "Grading & Report Cards",
            "summary": "Configurable scales, assessments, and published reports.",
            "path": _safe_reverse("marketing_platform_grading_report_cards")
            or "/platform/grading-report-cards/",
            "screenshot_static": "images/marketing/viz-student360.svg",
        },
        {
            "title": "Parent Portal",
            "summary": "Mobile-friendly clarity on fees, attendance, and results.",
            "path": _safe_reverse("marketing_platform_parent_portal")
            or "/platform/parent-portal/",
            "screenshot_static": "images/marketing/module-communication.svg",
        },
        {
            "title": "Teacher Portal",
            "summary": "Registers, marks, assignments, and messaging in one workspace.",
            "path": _safe_reverse("marketing_platform_teacher_portal")
            or "/platform/teacher-portal/",
            "screenshot_static": "images/marketing/viz-teacher.svg",
        },
        {
            "title": "Student Portal",
            "summary": "Schedules, coursework, resources, and announcements.",
            "path": _safe_reverse("marketing_platform_student_portal")
            or "/platform/student-portal/",
            "screenshot_static": "images/marketing/illustration-students.svg",
        },
        {
            "title": "Communications",
            "summary": "Official broadcasts with governance—not shadow channels.",
            "path": _safe_reverse("marketing_platform_communications")
            or "/platform/communications/",
            "screenshot_static": "images/marketing/module-communication.svg",
        },
        {
            "title": "Analytics & Dashboards",
            "summary": "Leadership-ready enrollment, attendance, and outcomes.",
            "path": _safe_reverse("marketing_platform_analytics")
            or "/platform/analytics/",
            "screenshot_static": "images/marketing/health-score-visual.svg",
        },
        {
            "title": "Workflow Automation",
            "summary": "Approvals across admissions, finance, and compliance.",
            "path": _safe_reverse("marketing_platform_workflows")
            or "/platform/workflows/",
            "screenshot_static": "images/marketing/illustration-workflow.svg",
        },
        {
            "title": "Offline-First Sync",
            "summary": "Resilience when connectivity drops anywhere you operate.",
            "path": _safe_reverse("marketing_platform_offline_first")
            or "/platform/offline-first/",
            "screenshot_static": "images/marketing/setup-studio-flow.svg",
        },
        {
            "title": "Security & Permissions",
            "summary": "Role-based access, audits, and multi-campus governance.",
            "path": _safe_reverse("marketing_platform_security")
            or "/platform/security/",
            "screenshot_static": "images/marketing/module-compliance.svg",
        },
    ]
    hero_ai_line = ""
    differentiation_block = [
        "Each campus keeps its own tenant boundary, branding, and data ownership.",
        "Operators see every school, queued offline work, and rollout risk in one place.",
        "Global-first configuration: currencies, languages, terms, and grading models.",
        "One product thread from inquiry to graduation—no duplicate entry across silos.",
    ]

    # Enterprise path
    enterprise_path_copy = "Need multi-campus governance, deeper audits, or tailored rollout? Book a solutions conversation."

    # Asset defaults: use static placeholders when settings are unset (no 404s). All required per Visual Asset plan.
    global_map_image_url = getattr(
        settings, "MARKETING_GLOBAL_MAP_IMAGE_URL", None
    ) or static("images/marketing/global-map.svg")
    illustration_workflow_url = getattr(
        settings, "MARKETING_ILLUSTRATION_WORKFLOW_URL", None
    ) or static("images/marketing/illustration-workflow.svg")
    illustration_globe_url = getattr(
        settings, "MARKETING_ILLUSTRATION_GLOBE_URL", None
    ) or static("images/marketing/illustration-globe.svg")
    illustration_students_url = getattr(
        settings, "MARKETING_ILLUSTRATION_STUDENTS_URL", None
    ) or static("images/marketing/illustration-students.svg")
    # Strategic diagram URLs (Batch 1/2; ultra high-end: dedicated SVGs per MARKETING_FRONT_PLACEHOLDER).
    _diagram_fallback = static("images/marketing/platform-diagram-marketing.svg")
    platform_architecture_diagram_url = (
        getattr(settings, "MARKETING_PLATFORM_ARCHITECTURE_DIAGRAM_URL", None)
        or _diagram_fallback
    )
    migration_cloud_diagram_url = getattr(
        settings, "MARKETING_MIGRATION_CLOUD_DIAGRAM_URL", None
    ) or static("images/marketing/migration-flow.svg")
    school_in_a_box_flow_image_url = getattr(
        settings, "MARKETING_SCHOOL_IN_A_BOX_FLOW_IMAGE_URL", None
    ) or static("images/marketing/setup-studio-flow.svg")
    data_intelligence_loop_image_url = (
        getattr(settings, "MARKETING_DATA_INTELLIGENCE_LOOP_IMAGE_URL", None)
        or _diagram_fallback
    )
    ecosystem_map_image_url = getattr(
        settings, "MARKETING_ECOSYSTEM_MAP_IMAGE_URL", None
    ) or static("images/marketing/ecosystem-diagram.svg")
    # §12 MARKETING_FRONT_PLACEHOLDER: wire all asset keys (templates use these).
    migration_diagram_url = (
        getattr(settings, "MARKETING_MIGRATION_DIAGRAM_URL", None)
        or migration_cloud_diagram_url
    )
    ecosystem_diagram_url = (
        getattr(settings, "MARKETING_ECOSYSTEM_DIAGRAM_URL", None)
        or ecosystem_map_image_url
    )
    control_plane_diagram_url = getattr(
        settings, "MARKETING_CONTROL_PLANE_DIAGRAM_URL", None
    ) or static("images/marketing/control-plane-diagram.svg")
    setup_studio_flow_image_url = getattr(
        settings, "MARKETING_SETUP_STUDIO_FLOW_IMAGE_URL", None
    ) or static("images/marketing/setup-studio-flow.svg")
    # §12 platform-grade: every asset slot has a non-empty fallback so marketing front never shows broken/empty sections.
    health_score_visual_url = getattr(
        settings, "MARKETING_HEALTH_SCORE_VISUAL_URL", None
    ) or static("images/marketing/health-score-visual.svg")
    role_preview_images = getattr(settings, "MARKETING_ROLE_PREVIEW_IMAGES", None) or [
        {
            "role": "owners",
            "label": "Owners",
            "image_url": "",
            "image_static": "images/marketing/health-score-visual.svg",
        },
        {
            "role": "administrator",
            "label": "Administrators",
            "image_url": "",
            "image_static": "images/marketing/viz-admin.svg",
        },
        {
            "role": "teacher",
            "label": "Teachers",
            "image_url": "",
            "image_static": "images/marketing/viz-teacher.svg",
        },
        {
            "role": "parent",
            "label": "Parents",
            "image_url": "",
            "image_static": "images/marketing/module-communication.svg",
        },
        {
            "role": "finance",
            "label": "Finance teams",
            "image_url": "",
            "image_static": "images/marketing/module-finance.svg",
        },
        {
            "role": "network",
            "label": "School networks",
            "image_url": "",
            "image_static": "images/marketing/illustration-students.svg",
        },
    ]

    # AI Intelligence section: dedicated homepage block (required).
    ai_intelligence_features = [
        "Predict at-risk students and recommend interventions.",
        "Surface insights for enrollment and retention.",
        "Automate routine reporting so staff focus on teaching.",
    ]
    ai_intelligence_cta_path = (
        _safe_reverse("marketing_products_analytics")
        or _safe_reverse("marketing_landing")
        or "/"
    )

    # CMS overrides (MarketingContent) — last wins over code defaults / geo / channel.
    hero_cms_ai_set = False
    try:
        _cms_h = _marketing_cms_plain("landing_hero_headline", language)
        if _cms_h:
            hero_headline = _cms_h[:500]
        _cms_s = _marketing_cms_plain("landing_hero_subheadline", language)
        if _cms_s:
            hero_subheadline = _cms_s[:1200]
        _cms_ai = _marketing_cms_plain("landing_hero_ai_line", language)
        if _cms_ai:
            hero_ai_line = _cms_ai[:1200]
            hero_cms_ai_set = True
    except (DatabaseError, OperationalError, AttributeError, TypeError, ValueError):
        pass

    # A/B hero_variant "B": append to hero_ai_line (template shows hero_ai_line before hero_subheadline).
    if hero_variant == "B" and not hero_cms_ai_set:
        _b_extra = getattr(settings, "MARKETING_HERO_VARIANT_B_SUBLINE", None)
        if isinstance(_b_extra, str) and _b_extra.strip():
            _b_line = _b_extra.strip()
        else:
            _b_line = (
                "Operator-grade visibility for one campus—or many—with audit-ready governance."
            )
        hero_ai_line = f"{hero_ai_line.rstrip()} {_b_line}".strip()

    if not (hero_ai_line or "").strip():
        hero_ai_line = hero_subheadline

    platform_headline = hero_headline

    return {
        "pitch": pitch,
        "brand": brand,
        "country_code": country,
        "language_code": language,
        "seo_title": pitch.get("seo_title"),
        "seo_description": pitch.get("seo_description"),
        "canonical_url": canonical_url,
        "hreflang_entries": hreflang_entries,
        "structured_data_json": json.dumps(structured_data),
        "marketing_nav": _marketing_nav(),
        "topical_nav": _topical_nav_featured(),
        "topical_nav_total": len(_topical_nav()),
        "canonical_domain": canonical_domain,
        "public_host": public_host,
        "manager_host": manager_host,
        "api_host": api_host,
        "docs_host": docs_host,
        "tenant_example_host": tenant_host,
        "surface_cards": surface_cards,
        "authority_metrics": authority_metrics,
        "proof_points": proof_points,
        "trust_badges": trust_badges,
        "rollout_steps": rollout_steps,
        "audience_segments": audience_segments,
        "proof_stats": proof_stats,
        "institution_logos": institution_logos,
        "admissions_flow": admissions_flow,
        "pricing_snapshot": pricing_snapshot,
        "trust_controls": trust_controls,
        "what_you_get": what_you_get,
        "post_enrollment_revenue": post_enrollment_revenue,
        "global_features": global_features,
        "hero_variant": hero_variant,
        "marketing_cta_variant": marketing_cta_variant,
        "demo_tenant_url": demo_tenant_url,
        "demo_what_you_see": getattr(settings, "MARKETING_DEMO_WHAT_YOU_SEE", None)
        or [],
        "marketing_product_tour_url": getattr(
            settings, "MARKETING_PRODUCT_TOUR_URL", None
        )
        or "",
        "marketing_newsletter_form_action": getattr(
            settings, "MARKETING_NEWSLETTER_FORM_ACTION", None
        )
        or "",
        "marketing_footer_tagline_html": _marketing_cms_html_for_key(
            "marketing_footer_tagline", language
        ),
        "marketing_newsletter_blurb_html": _marketing_cms_html_for_key(
            "marketing_newsletter_blurb", language
        ),
        "marketing_analytics_script_url": marketing_analytics_script_url,
        "marketing_analytics_endpoint_url": marketing_analytics_endpoint_url,
        "marketing_page_type": "WebSite",
        "marketing_page_slug": "home",
        "marketing_analytics_preconnect_origin": marketing_analytics_preconnect_origin,
        "SHOW_HEADER_CONTEXT_STRIP": False,
        "marketing_show_chapter_indicator": False,
        "marketing_show_hero_sandbox_link": False,
        "marketing_show_marketing_nav_chips": False,
        # Landing revamp: outcome-focused copy and 10-section context
        "marketing_navbar_primary": (nav_primary := _marketing_navbar_primary()),
        "marketing_navbar_visible_count": MARKETING_NAVBAR_VISIBLE_COUNT,
        "marketing_navbar_has_more": len(nav_primary) > MARKETING_NAVBAR_VISIBLE_COUNT,
        "marketing_navbar_more_mega_columns": _marketing_more_nav_mega_columns(),
        "hero_headline": hero_headline,
        "hero_subheadline": hero_subheadline,
        "hero_ctas": hero_ctas,
        "trust_logos": trust_logos,
        "core_modules": core_modules,
        "platform_cards": platform_cards,
        "migration_bullets": migration_bullets,
        "scales_globally_line": scales_globally_line,
        "three_key_features": three_key_features,
        "migration_studio_image_url": migration_studio_image_url,
        "ecosystem_apps": ecosystem_apps,
        "testimonials": testimonials,
        "video_testimonials": video_testimonials,
        "security_badges": security_badges,
        "final_cta_headline": final_cta_headline,
        "hero_dashboard_image_url": hero_dashboard_image_url,
        "proof_hero_image_key": proof_hero_image_key,
        "hero_dashboard_image_srcset": getattr(
            settings, "MARKETING_HERO_IMAGE_SRCSET", None
        )
        or "",
        "hero_dashboard_image_sizes": getattr(
            settings, "MARKETING_HERO_IMAGE_SIZES", None
        )
        or "(max-width: 800px) 100vw, 800px",
        "hero_video_url": hero_video_url,
        "hero_video_poster_url": hero_video_poster_url,
        "product_demo_image_url": product_demo_image_url,
        "product_visualization_slides": product_visualization_slides,
        "organization_schema_json": organization_schema_json,
        "geo_copy": _geo_copy_variations(country),
        "marketing_calendly_url": getattr(settings, "MARKETING_CALENDLY_URL", None)
        or "",
        "institution_types": institution_types,
        "workflow_automation": workflow_automation,
        "developer_platform_card": developer_platform_card,
        "platform_headline": platform_headline,
        "category_claim": category_claim,
        "platform_pillar_grid": platform_pillar_grid,
        "from_single_to_enterprise": from_single_to_enterprise,
        "by_the_numbers": by_the_numbers,
        "outcome_metrics": outcome_metrics,
        "global_map_image_url": global_map_image_url,
        "global_stats": getattr(settings, "MARKETING_GLOBAL_STATS", None)
        or [
            {"label": "Operating model", "value": "Configurable"},
            {"label": "Currencies & fees", "value": "Multi-currency"},
            {"label": "Portals", "value": "Role-based"},
        ],
        "illustration_workflow_url": illustration_workflow_url,
        "illustration_globe_url": illustration_globe_url,
        "illustration_students_url": illustration_students_url,
        "platform_architecture_diagram_url": platform_architecture_diagram_url,
        "migration_cloud_diagram_url": migration_cloud_diagram_url,
        "school_in_a_box_flow_image_url": school_in_a_box_flow_image_url,
        "data_intelligence_loop_image_url": data_intelligence_loop_image_url,
        "ecosystem_map_image_url": ecosystem_map_image_url,
        "migration_diagram_url": migration_diagram_url,
        "ecosystem_diagram_url": ecosystem_diagram_url,
        "control_plane_diagram_url": control_plane_diagram_url,
        "setup_studio_flow_image_url": setup_studio_flow_image_url,
        "health_score_visual_url": health_score_visual_url,
        "role_preview_images": role_preview_images,
        "ai_intelligence_features": ai_intelligence_features,
        "ai_intelligence_cta_path": ai_intelligence_cta_path,
        "customer_logos": customer_logos,
        "awards_recognition": awards_recognition,
        "review_badges": review_badges,
        "ten_reasons_page_path": ten_reasons_page_path,
        "for_your_role": for_your_role,
        "solve_by_challenge": solve_by_challenge,
        "app_marketplace_hero": app_marketplace_hero,
        "developer_story_summary": developer_story_summary,
        "partners_list": partners_list,
        "integrations_strip": integrations_strip,
        "gated_report_cta": gated_report_cta,
        "second_lead_magnet": second_lead_magnet,
        "resources_hub_path": resources_hub_path,
        "events_list": events_list,
        "flagship_event": flagship_event,
        "community_cta": community_cta,
        "support_implementation_copy": support_implementation_copy,
        "accessibility_line": accessibility_line,
        "why_switch_path": why_switch_path,
        "why_switch_bullets": why_switch_bullets,
        "get_started_three_steps": get_started_three_steps,
        "product_pillars_home": product_pillars_home,
        "hero_ai_line": hero_ai_line,
        "differentiation_block": differentiation_block,
        "enterprise_path_copy": enterprise_path_copy,
        # §8.4 MARKETING_FRONT_PLACEHOLDER: safe defaults so templates can reference without KeyError
        "comparison_table": getattr(settings, "MARKETING_COMPARISON_TABLE", None) or [],
        "replacement_messaging": getattr(
            settings, "MARKETING_REPLACEMENT_MESSAGING", None
        )
        or {},
        "marketing_story_journey": [
            {
                "phase": "Morning chaos",
                "copy": "Forms, fees, and parent messages live in different tools — until they don't.",
            },
            {
                "phase": "One search",
                "copy": "Ctrl+K surfaces each student with class context, fee posture, and recent guardian messages.",
            },
            {
                "phase": "Super-admin calm",
                "copy": "Automations handle reminders and reconciliation; you work exceptions from Student 360.",
            },
        ],
        "marketing_data_flow_chain": [
            {"label": "Inquiry", "detail": "Campaign-aware intake"},
            {"label": "Admission", "detail": "Pipeline & decisions"},
            {"label": "Enrollment", "detail": "Activated student record"},
            {"label": "Class placement", "detail": "Roster without re-entry"},
            {"label": "Invoice", "detail": "Fees tied to enrollment"},
            {"label": "Attendance", "detail": "Daily posture captured"},
            {"label": "Assessment", "detail": "Marks with oversight"},
            {"label": "Report card", "detail": "Published to guardians"},
            {"label": "Parent portal", "detail": "Fees, grades, attendance, announcements"},
            {"label": "Leadership analytics", "detail": "Roll-ups leaders defend in review"},
        ],
        "marketing_apac_story": None,
        "marketing_admin_efficiency_note": (
            "In-product automation — fee reminders, receipt workflows, attendance pipelines — is designed to "
            "replace repetitive manual steps. We encourage each school to measure time saved after go-live "
            "rather than publishing a one-size-fits-all percentage."
        ),
    }


def _organization_schema(canonical_base_url: str) -> dict:
    """Schema.org Organization for RunMyCampus (Wave 2 SEO)."""
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "RunMyCampus",
        "url": canonical_base_url,
        "description": "RunMyCampus is a global school operations platform for admissions, academics, finance, and compliance.",
        "applicationCategory": "EducationalApplication",
    }


def _faq_schema(faq_list: list[dict], canonical_url: str) -> dict:
    """Schema.org FAQPage from list of {question, answer} (Wave 2 SEO)."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "url": canonical_url,
        "mainEntity": [
            {
                "@type": "Question",
                "name": faq["question"],
                "acceptedAnswer": {"@type": "Answer", "text": faq["answer"]},
            }
            for faq in faq_list
        ],
    }


def _breadcrumb_list_schema(
    canonical_base_url: str, path_segments: list[tuple[str, str]]
) -> dict:
    """Schema.org BreadcrumbList from (name, path) segments. path is relative (e.g. /, /product/)."""
    base = canonical_base_url.rstrip("/")
    items = []
    for i, (name, path) in enumerate(path_segments, 1):
        p = path if path.startswith("/") else "/" + path
        item_url = base + p if p != "/" else base + "/"
        items.append(
            {
                "@type": "ListItem",
                "position": i,
                "name": name,
                "item": item_url,
            }
        )
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items,
    }


def _structured_data_for_page(
    *, page_type: str, canonical_url: str, name: str, description: str, path: str
) -> dict:
    base_url = (
        canonical_url.rsplit(path, 1)[0] + "/"
        if path in canonical_url
        else canonical_url
    )
    payload: dict = {
        "@context": "https://schema.org",
        "@type": page_type,
        "name": name,
        "url": canonical_url,
        "description": description,
        "isPartOf": {"@type": "WebSite", "name": "RunMyCampus", "url": base_url},
    }
    if page_type == "OfferCatalog":
        payload["itemListElement"] = [
            {
                "@type": "Offer",
                "name": "Starter",
                "description": "For single-campus schools: admissions, academics, portals.",
            },
            {
                "@type": "Offer",
                "name": "Growth",
                "description": "For expanding networks: multi-campus, localization, support visibility.",
            },
            {
                "@type": "Offer",
                "name": "Enterprise",
                "description": "White-label for national scale: manager operations, API, compliance.",
            },
        ]
    if page_type == "ItemList":
        payload["itemListElement"] = [
            {"@type": "ListItem", "position": 1, "name": "LTI interoperability"},
            {"@type": "ListItem", "position": 2, "name": "Payment gateways"},
            {"@type": "ListItem", "position": 3, "name": "Messaging providers"},
        ]
    if page_type == "Service":
        payload["provider"] = {"@type": "Organization", "name": "RunMyCampus"}
        payload["serviceType"] = "School management platform demonstration"
    return payload


def _marketing_base_context(request) -> dict:
    geo_country = _get_country_from_request(request)
    return _marketing_context(
        request,
        country_code=geo_country,
        language_code=(getattr(request, "LANGUAGE_CODE", "") or "en"),
        regional=False,
    )


@require_GET
def marketing_landing(request):
    """Global marketing landing with geo-personalized copy."""
    from apps.schools.funnel_events import record_marketing_funnel_event

    record_marketing_funnel_event("visit", request)
    geo_country = _get_country_from_request(request)
    ctx = _marketing_context(
        request,
        country_code=geo_country,
        language_code=(getattr(request, "LANGUAGE_CODE", "") or "en"),
        regional=False,
    )
    return render(request, "schools/marketing_landing.html", ctx)


def _get_blog_posts(limit: int = 20):
    """Return published blog posts for marketing blog page; empty list if model unavailable."""
    try:
        from apps.siteconfig.models import BlogPost

        return list(
            BlogPost.objects.filter(is_published=True).order_by(
                "-published_at", "-created_at"
            )[:limit]
        )
    except (ImportError, DatabaseError, OperationalError, AttributeError, TypeError):
        return []


def _marketing_cms_rows_for_locale(language_code: str) -> dict:
    """
    Map MarketingContent.key -> row; locale-specific overrides win over blank locale.
    """
    try:
        from apps.siteconfig.models_marketing import MarketingContent
    except ImportError:
        return {}
    short = (language_code or "en").split("-")[0].lower()[:10] or "en"
    try:
        rows = MarketingContent.objects.filter(Q(locale="") | Q(locale=short))
    except (DatabaseError, OperationalError, TypeError, ValueError):
        return {}
    priority = {"": 0, short: 1}
    by_key: dict[str, tuple[int, object]] = {}
    for r in rows:
        p = priority.get(r.locale, 0)
        prev = by_key.get(r.key)
        if not prev or p > prev[0]:
            by_key[r.key] = (p, r)
    return {k: v[1] for k, v in by_key.items()}


def _marketing_cms_plain(key: str, language_code: str) -> str:
    from django.utils.html import strip_tags

    row = _marketing_cms_rows_for_locale(language_code).get(key)
    if not row or not getattr(row, "content_html", None):
        return ""
    return strip_tags(row.content_html).strip()


def _marketing_cms_html_for_key(key: str, language_code: str) -> str:
    row = _marketing_cms_rows_for_locale(language_code).get(key)
    if not row or not getattr(row, "content_html", None):
        return ""
    return row.content_html


@require_GET
def blog_post_detail(request, slug: str):
    """Single blog post at /blog/<slug>/."""
    try:
        from apps.siteconfig.models import BlogPost

        post = BlogPost.objects.filter(slug=slug, is_published=True).first()
    except (ImportError, DatabaseError, OperationalError, AttributeError, TypeError):
        post = None
    if not post:
        raise Http404("Blog post not found")

    base_ctx = _marketing_base_context(request)
    canonical_path = f"/blog/{post.slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    ctx = {
        **base_ctx,
        "seo_title": post.title,
        "seo_description": (post.excerpt or post.title)[:160],
        "canonical_url": canonical_url,
        "post": post,
        "active_nav_slug": "blog",
    }
    return render(request, "schools/marketing_blog_detail.html", ctx)


@require_GET
def marketing_page(request, page_slug: str):
    normalized_slug = (page_slug or "").strip().lower()
    reg_s, var_s = _marketing_content_file_params()
    loaded = _load_marketing_page_from_file(
        normalized_slug, region=reg_s, variant=var_s
    )
    if loaded:
        page_copy = deepcopy(loaded[0])
        page_extras = deepcopy(loaded[1])
    else:
        page = MARKETING_PAGE_DEFINITIONS.get(normalized_slug)
        if not page:
            raise Http404("Page not found")
        page_copy = deepcopy(page)
        page_extras = deepcopy(MARKETING_PAGE_EXTRAS.get(normalized_slug, {}))
    base_ctx = _marketing_base_context(request)
    slug_based_path = f"/{page_slug}/"
    canonical_path = (
        (request.path if request.path.endswith("/") else request.path + "/")
        if (getattr(request, "path", None) and request.path != slug_based_path)
        else slug_based_path
    )
    canonical_url = _absolute_url(request, canonical_path)
    page_copy["slug"] = page_slug
    page_copy["path"] = canonical_path

    structured_data = _structured_data_for_page(
        page_type=page_copy.get("schema_type") or "WebPage",
        canonical_url=canonical_url,
        name=page_copy.get("label") or "RunMyCampus",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )

    blog_posts = (
        _get_blog_posts() if page_slug in ("blog", "resources-blog") else []
    )
    blog_list_intro_html = ""
    if normalized_slug == "blog":
        try:
            blog_list_intro_html = _marketing_cms_html_for_key(
                "blog_list_intro",
                getattr(request, "LANGUAGE_CODE", "") or "en",
            )
        except (DatabaseError, OperationalError, AttributeError, TypeError, ValueError):
            blog_list_intro_html = ""
    faq_schema_json = ""
    if page_extras.get("faqs"):
        faq_schema_json = json.dumps(_faq_schema(page_extras["faqs"], canonical_url))

    # BreadcrumbList schema: Home > Page label
    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [
        ("Home", "/"),
        (page_copy.get("label") or page_slug, canonical_path),
    ]
    breadcrumb_schema_json = json.dumps(
        _breadcrumb_list_schema(base_url, breadcrumb_segments)
    )

    # Wave 3: SLA/uptime status URL from settings for trust-center and uptime
    if page_slug in ("trust-center", "uptime") and page_extras.get("sla_uptime"):
        status_url = getattr(settings, "MARKETING_STATUS_PAGE_URL", None) or ""
        page_extras["sla_uptime"] = {
            **page_extras["sla_uptime"],
            "status_url": status_url,
        }

    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "faq_schema_json": faq_schema_json,
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "page": page_copy,
        "page_extras": page_extras,
        "active_nav_slug": page_slug,
        "marketing_page_type": page_copy.get("schema_type") or "WebPage",
        "marketing_page_slug": page_slug,
        "blog_posts": blog_posts,
        "blog_list_intro_html": blog_list_intro_html,
        "powerhouse_highlights": [
            "Predictive risk scoring and intervention action-center workflows.",
            "Student passport and transcript portability across schools.",
            "Super-admin mission control for approvals, billing, and support.",
        ],
    }
    # Product page: product-led storytelling (micro-demos, scroll-driven dark-mode, outcome-focused, developer-centric)
    if normalized_slug == "product":
        return render(request, "schools/marketing_product_page.html", ctx)
    type_tpl = _marketing_page_type_template(normalized_slug)
    return render(
        request,
        type_tpl if type_tpl else "schools/marketing_page.html",
        ctx,
    )


@require_POST
@csrf_protect
def submit_demo_request(request):
    """
    Accept book-a-demo form POST (name, email, school, message, plus optional context fields).
    If MARKETING_DEMO_WEBHOOK_URL is set, POST JSON to it; then redirect to /demo/ with ?submitted=1 or ?error=1.
    """
    name = (request.POST.get("name") or "").strip()[:256]
    email = (request.POST.get("email") or "").strip()[:256]
    school = (request.POST.get("school") or "").strip()[:256]
    message = (request.POST.get("message") or "").strip()[:2000]
    phone = (request.POST.get("phone") or "").strip()[:64]
    country = (request.POST.get("country") or "").strip()[:128]
    school_type = (request.POST.get("school_type") or "").strip()[:128]
    student_count = (request.POST.get("student_count") or "").strip()[:64]
    detail_lines = []
    if phone:
        detail_lines.append(f"Phone: {phone}")
    if country:
        detail_lines.append(f"Country: {country}")
    if school_type:
        detail_lines.append(f"School type: {school_type}")
    if student_count:
        detail_lines.append(f"Student count: {student_count}")
    message_for_store = message
    if detail_lines:
        suffix = "\n\n" + "\n".join(detail_lines)
        message_for_store = (message + suffix).strip()[:4000]
    webhook_url = getattr(settings, "MARKETING_DEMO_WEBHOOK_URL", None) or ""
    success = False
    if webhook_url and email:
        payload = json.dumps(
            {
                "name": name,
                "email": email,
                "school": school,
                "message": message_for_store,
                "phone": phone,
                "country": country,
                "school_type": school_type,
                "student_count": student_count,
            }
        )
        try:
            from urllib.request import Request, urlopen
            from urllib.error import URLError, HTTPError

            req = Request(
                webhook_url,
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urlopen(req, timeout=10)
            success = True
        except (URLError, HTTPError, OSError):
            pass
    elif email:
        # No webhook configured; still count as success so user sees confirmation (admin can check logs or add webhook later)
        success = True
    if success:
        try:
            from apps.schools.funnel_events import record_marketing_funnel_event

            record_marketing_funnel_event("demo_started", request)
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
    redirect_url = reverse("marketing_demo")
    if success:
        redirect_url += "?submitted=1"
    else:
        redirect_url += "?error=1"
    return redirect(redirect_url)


@require_POST
@csrf_protect
def submit_contact_request(request):
    """
    Contact form POST (sales, implementation, support routing, partnerships, general).

    Webhook JSON POST when ``MARKETING_CONTACT_WEBHOOK_URL`` is set (see ``config/settings.py``).
    If unset, falls back to ``MARKETING_DEMO_WEBHOOK_URL`` so operators can reuse one inbound endpoint.
    Missing/unreachable webhooks still redirect with ``?submitted=1`` when ``email`` is present so UX does not dead-end.

    Redirects to ``marketing_contact`` with ``?submitted=1`` or ``?error=1``. GET returns 405 (POST-only route).
    """
    name = (request.POST.get("name") or "").strip()[:256]
    email = (request.POST.get("email") or "").strip()[:256]
    school = (request.POST.get("school") or "").strip()[:256]
    country = (request.POST.get("country") or "").strip()[:128]
    inquiry_type = (request.POST.get("inquiry_type") or "").strip()[:64]
    message = (request.POST.get("message") or "").strip()[:4000]
    webhook_url = getattr(settings, "MARKETING_CONTACT_WEBHOOK_URL", None) or getattr(
        settings, "MARKETING_DEMO_WEBHOOK_URL", None
    ) or ""
    success = False
    payload_obj = {
        "source": "marketing_contact",
        "name": name,
        "email": email,
        "school": school,
        "country": country,
        "inquiry_type": inquiry_type,
        "message": message,
    }
    if webhook_url and email:
        payload = json.dumps(payload_obj)
        try:
            from urllib.request import Request, urlopen
            from urllib.error import URLError, HTTPError

            req = Request(
                webhook_url,
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urlopen(req, timeout=10)
            success = True
        except (URLError, HTTPError, OSError):
            pass
    elif email:
        success = True
    redirect_url = reverse("marketing_contact")
    if success:
        redirect_url += "?submitted=1"
    else:
        redirect_url += "?error=1"
    return redirect(redirect_url)


@require_POST
@csrf_protect
def submit_security_packet_request(request):
    """
    Dedicated security / procurement packet request (distinct from general contact).

    Webhook uses same env as contact when unset. Payload ``source`` is
    ``security_packet_request`` for downstream routing.
    """
    name = (request.POST.get("name") or "").strip()[:256]
    email = (request.POST.get("email") or "").strip()[:256]
    organization = (request.POST.get("organization") or "").strip()[:256]
    role = (request.POST.get("role") or "").strip()[:128]
    country = (request.POST.get("country") or "").strip()[:128]
    nda_status = (request.POST.get("nda_status") or "").strip()[:128]
    artifact_needs = (request.POST.get("artifact_needs") or "").strip()[:4000]
    webhook_url = getattr(settings, "MARKETING_CONTACT_WEBHOOK_URL", None) or getattr(
        settings, "MARKETING_DEMO_WEBHOOK_URL", None
    ) or ""
    success = False
    payload_obj = {
        "source": "security_packet_request",
        "name": name,
        "email": email,
        "organization": organization,
        "role": role,
        "country": country,
        "nda_status": nda_status,
        "artifact_needs": artifact_needs,
    }
    if webhook_url and email:
        payload = json.dumps(payload_obj)
        try:
            from urllib.error import HTTPError, URLError
            from urllib.request import Request, urlopen

            req = Request(
                webhook_url,
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urlopen(req, timeout=10)
            success = True
        except (URLError, HTTPError, OSError):
            pass
    elif email:
        success = True
    redirect_url = reverse("marketing_security_packet_request")
    if success:
        redirect_url += "?submitted=1"
    else:
        redirect_url += "?error=1"
    return redirect(redirect_url)


# Wave 3: Downloadable buyer toolkit and implementation checklist
_BUYER_CHECKLIST_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>RunMyCampus Buyer Evaluation Checklist</title></head>
<body>
<h1>RunMyCampus Buyer Evaluation Checklist</h1>
<p>Use this checklist before you commit. RunMyCampus — The Operating System for Modern Schools.</p>
<h2>Tenancy &amp; architecture</h2>
<ul>
<li>[ ] Subdomain-based tenant isolation (not path-based)</li>
<li>[ ] Dedicated manager host for support and governance</li>
<li>[ ] Clear public / tenant / manager host contract</li>
</ul>
<h2>Security &amp; compliance</h2>
<ul>
<li>[ ] FERPA / GDPR alignment and regional compliance defaults</li>
<li>[ ] Audit trails for admin and support actions</li>
<li>[ ] Encryption at rest and in transit</li>
<li>[ ] Role-based access controls</li>
</ul>
<h2>Localization</h2>
<ul>
<li>[ ] Multi-language and multi-currency support</li>
<li>[ ] Country-specific grading and terminology</li>
<li>[ ] Data residency options</li>
</ul>
<h2>Support &amp; operations</h2>
<ul>
<li>[ ] 24/7 operator readiness and support visibility</li>
<li>[ ] Migration tools and guided setup</li>
<li>[ ] API and documentation host</li>
</ul>
<p>Downloaded from runmycampus.com. &copy; RunMyCampus.</p>
</body>
</html>
"""

_IMPLEMENTATION_CHECKLIST_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>RunMyCampus Implementation Checklist</title></head>
<body>
<h1>RunMyCampus Implementation Checklist</h1>
<p>Phased rollout with role ownership. Track progress by phase.</p>
<h2>Phase 1 — Discovery and signup (Owner: School lead)</h2>
<ul>
<li>[ ] Evaluate platform fit and compare architecture</li>
<li>[ ] Start free trial</li>
<li>[ ] Confirm data and compliance requirements</li>
</ul>
<h2>Phase 2 — Tenant and data setup (Owner: IT)</h2>
<ul>
<li>[ ] Provision tenant and configure branding</li>
<li>[ ] Import students and staff</li>
<li>[ ] Configure SSO and integrations (LMS, payments, messaging)</li>
</ul>
<h2>Phase 3 — Finance and billing (Owner: Finance)</h2>
<ul>
<li>[ ] Configure fee structure and payment terms</li>
<li>[ ] Connect payment gateway</li>
<li>[ ] Run first billing cycle and reconcile</li>
</ul>
<h2>Phase 4 — Academics and go-live (Owner: Admissions / Academics)</h2>
<ul>
<li>[ ] Configure grading, terms, and report cards</li>
<li>[ ] Train teachers and staff</li>
<li>[ ] Go live and monitor; hand off to support</li>
</ul>
<p>Downloaded from runmycampus.com. &copy; RunMyCampus.</p>
</body>
</html>
"""


@require_GET
def buyer_toolkit_download(request, document: str):
    """Serve downloadable buyer or implementation checklist as HTML (save as PDF from browser)."""
    if document == "implementation-checklist":
        content = _IMPLEMENTATION_CHECKLIST_HTML
        filename = "runmycampus-implementation-checklist.html"
    elif document == "buyer-checklist":
        content = _BUYER_CHECKLIST_HTML
        filename = "runmycampus-buyer-evaluation-checklist.html"
    else:
        raise Http404("Document not found")
    response = HttpResponse(content, content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_GET
@staff_member_required(login_url=settings.LOGIN_URL)
def marketing_funnel_dashboard(request):
    """Wave 4+: Conversion funnel + growth analytics (billing-linked, no fake KPIs). Staff only."""
    from apps.schools.growth_analytics import build_growth_funnel_snapshot
    from apps.schools.models import MarketingFunnelEvent

    now = timezone.now()
    all_time = MarketingFunnelEvent.objects.values("event_type").annotate(
        count=Count("id")
    )
    all_time_map = {r["event_type"]: r["count"] for r in all_time}
    visit = all_time_map.get("visit", 0)
    discovery = all_time_map.get("discovery", 0)
    signup = all_time_map.get("signup", 0)
    activation = all_time_map.get("activation", 0)

    # Last 7 and 30 days
    from datetime import timedelta

    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    last7 = (
        MarketingFunnelEvent.objects.filter(created_at__gte=week_ago)
        .values("event_type")
        .annotate(count=Count("id"))
    )
    last30 = (
        MarketingFunnelEvent.objects.filter(created_at__gte=month_ago)
        .values("event_type")
        .annotate(count=Count("id"))
    )
    last7_map = {r["event_type"]: r["count"] for r in last7}
    last30_map = {r["event_type"]: r["count"] for r in last30}

    # By channel (utm_source / utm_medium) for last 30 days
    channel_qs = (
        MarketingFunnelEvent.objects.filter(created_at__gte=month_ago)
        .values("utm_source", "utm_medium")
        .annotate(
            visit=Count("id", filter=Q(event_type="visit")),
            discovery=Count("id", filter=Q(event_type="discovery")),
            demo_started=Count("id", filter=Q(event_type="demo_started")),
            signup=Count("id", filter=Q(event_type="signup")),
            signup_completed=Count("id", filter=Q(event_type="signup_completed")),
            activation=Count("id", filter=Q(event_type="activation")),
            first_dashboard_view=Count(
                "id", filter=Q(event_type="first_dashboard_view")
            ),
            subscription_started=Count(
                "id", filter=Q(event_type="subscription_started")
            ),
        )
        .order_by("-visit")
    )
    channel_breakdown = [
        {
            "utm_source": r.get("utm_source") or "",
            "utm_medium": r.get("utm_medium") or "",
            "visit": r.get("visit", 0),
            "discovery": r.get("discovery", 0),
            "demo_started": r.get("demo_started", 0),
            "signup": r.get("signup", 0),
            "signup_completed": r.get("signup_completed", 0),
            "activation": r.get("activation", 0),
            "first_dashboard_view": r.get("first_dashboard_view", 0),
            "subscription_started": r.get("subscription_started", 0),
        }
        for r in channel_qs
    ]

    growth_snapshot = build_growth_funnel_snapshot(days=30)

    base_ctx = _marketing_base_context(request)
    ctx = {
        **base_ctx,
        "visit": visit,
        "discovery": discovery,
        "signup": signup,
        "activation": activation,
        "last7": last7_map,
        "last30": last30_map,
        "channel_breakdown": channel_breakdown,
        "growth": growth_snapshot,
    }
    return render(request, "schools/marketing_funnel_dashboard.html", ctx)


@require_GET
def topical_marketing_landing(request, topic_slug: str):
    topic = TOPICAL_LANDING_DEFINITIONS.get((topic_slug or "").strip().lower())
    if not topic:
        raise Http404("Topic not found")

    base_ctx = _marketing_base_context(request)
    canonical_path = f"/solutions/{topic_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    topic_copy = deepcopy(topic)
    topic_copy["slug"] = topic_slug
    topic_copy["path"] = canonical_path
    related_slugs = topic_copy.get("related_slugs") or []
    topic_copy["related_topics"] = [
        {"slug": s, "label": TOPICAL_LANDING_DEFINITIONS.get(s, {}).get("label", s)}
        for s in related_slugs
        if s
    ]

    structured_data = _structured_data_for_page(
        page_type="CollectionPage",
        canonical_url=canonical_url,
        name=topic_copy.get("label") or "RunMyCampus",
        description=topic_copy.get("seo_description") or "",
        path=canonical_path,
    )

    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [
        ("Home", "/"),
        ("Solutions", "/solutions/"),
        (topic_copy.get("label") or topic_slug, canonical_path),
    ]
    breadcrumb_schema_json = json.dumps(
        _breadcrumb_list_schema(base_url, breadcrumb_segments)
    )

    ctx = {
        **base_ctx,
        "seo_title": topic_copy.get("seo_title"),
        "seo_description": topic_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "topic": topic_copy,
        "active_nav_slug": "solutions",
    }
    return render(request, "schools/marketing_topic_page.html", ctx)


@require_GET
def institution_marketing_page(request, institution_slug: str):
    """Institutional segment landing: K-12, universities, technical-schools, private-schools, government-education."""
    definition = INSTITUTION_LANDING_DEFINITIONS.get(
        (institution_slug or "").strip().lower()
    )
    if not definition:
        raise Http404("Institution segment not found")
    base_ctx = _marketing_base_context(request)
    canonical_path = f"/solutions/{institution_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    premium = INSTITUTION_PREMIUM_LAYER.get((institution_slug or "").strip().lower())
    if premium:
        page_copy.update(deepcopy(premium))
    page_copy["slug"] = institution_slug
    structured_data = _structured_data_for_page(
        page_type="CollectionPage",
        canonical_url=canonical_url,
        name=page_copy.get("label") or "RunMyCampus",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )
    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [
        ("Home", "/"),
        ("Solutions", "/solutions/"),
        (page_copy.get("label") or institution_slug, canonical_path),
    ]
    breadcrumb_schema_json = json.dumps(
        _breadcrumb_list_schema(base_url, breadcrumb_segments)
    )
    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "page": page_copy,
        "active_nav_slug": "solutions",
        "institution_segment_slug": (institution_slug or "").strip().lower(),
    }
    return render(request, "marketing/marketing_institution_page.html", ctx)


@require_GET
def role_marketing_page(request, role_slug: str):
    """Role-based landing: school-admin, teachers, parents, students, it-directors, government."""
    definition = ROLE_PAGE_DEFINITIONS.get((role_slug or "").strip().lower())
    if not definition:
        raise Http404("Role page not found")
    base_ctx = _marketing_base_context(request)
    canonical_path = f"/roles/{role_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    page_copy["slug"] = role_slug
    structured_data = _structured_data_for_page(
        page_type="WebPage",
        canonical_url=canonical_url,
        name=page_copy.get("label") or "RunMyCampus",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )
    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [
        ("Home", "/"),
        ("Roles", "/roles/"),
        (page_copy.get("label") or role_slug, canonical_path),
    ]
    breadcrumb_schema_json = json.dumps(
        _breadcrumb_list_schema(base_url, breadcrumb_segments)
    )
    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "page": page_copy,
        "active_nav_slug": "solutions",
    }
    return render(request, "marketing/marketing_role_page.html", ctx)


@require_GET
def migrate_marketing_page(request, source_slug: str | None = None):
    """Migration landing: /migrate/ (generic) or /migrate/from-power-school/ etc."""
    slug_key = (source_slug or "").strip().lower() if source_slug else ""
    definition = MIGRATE_PAGE_DEFINITIONS.get(slug_key)
    if not definition:
        raise Http404("Migration page not found")
    base_ctx = _marketing_base_context(request)
    canonical_path = f"/migrate/{source_slug}/" if source_slug else "/migrate/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    page_copy["slug"] = slug_key
    structured_data = _structured_data_for_page(
        page_type="WebPage",
        canonical_url=canonical_url,
        name="Migrate to RunMyCampus",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )
    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [("Home", "/"), ("Migrate", "/migrate/")]
    if slug_key:
        breadcrumb_segments.append(
            (page_copy.get("headline", "Migration"), canonical_path)
        )
    breadcrumb_schema_json = json.dumps(
        _breadcrumb_list_schema(base_url, breadcrumb_segments)
    )
    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "page": page_copy,
        "active_nav_slug": "compare",
    }
    return render(request, "marketing/marketing_migrate_page.html", ctx)


@require_GET
def migration_simulator_page(request):
    """Migration simulator: select source and see steps, timeline, and field mapping (backend-driven)."""
    source_slug = (request.GET.get("source") or "").strip().lower()
    sources_list = [
        {
            "source_id": sid,
            "display_name": data["display_name"],
            "typical_timeline": data["typical_timeline"],
        }
        for sid, data in MIGRATION_SIMULATOR_SOURCES.items()
    ]
    selected = MIGRATION_SIMULATOR_SOURCES.get(source_slug) if source_slug else None
    if (
        request.headers.get("Accept", "").find("application/json") >= 0
        or request.GET.get("format") == "json"
    ):
        payload = {"sources": sources_list}
        if selected:
            payload["selected"] = {
                "source_id": selected["source_id"],
                "display_name": selected["display_name"],
                "typical_timeline": selected["typical_timeline"],
                "steps": selected["steps"],
                "field_mapping_examples": selected["field_mapping_examples"],
            }
        return JsonResponse(payload)
    base_ctx = _marketing_base_context(request)
    canonical_path = "/migrate/simulator/"
    canonical_url = _absolute_url(request, canonical_path)
    ctx = {
        **base_ctx,
        "seo_title": "Migration simulator | RunMyCampus",
        "seo_description": "See migration steps, timeline, and field mapping for PowerSchool, Blackbaud, Infinite Campus, or spreadsheets.",
        "canonical_url": canonical_url,
        "sources": sources_list,
        "selected_source": selected,
        "selected_slug": source_slug or None,
        "active_nav_slug": "compare",
    }
    return render(request, "marketing/marketing_migration_simulator.html", ctx)


def _setup_simulator_cta_url(request, cta_slug):
    """Resolve CTA slug to absolute URL for setup simulator steps."""
    slug_to_name = {
        "signup": "signup_school",
        "onboard": "onboard_wizard",
        "themes": "marketing_themes",
        "product": "marketing_product",
        "migrate": "migrate_marketing_page",
        "book-demo": "marketing_demo",
    }
    name = slug_to_name.get((cta_slug or "").strip())
    if not name:
        return None
    try:
        path = reverse(name)
        return request.build_absolute_uri(path)
    except (NoReverseMatch, ValueError, TypeError):
        return None


@require_GET
def setup_simulator_page(request):
    """Getting-started / setup simulator: six steps with CTAs (backend-driven)."""
    base_ctx = _marketing_base_context(request)
    canonical_path = "/getting-started/simulator/"
    canonical_url = _absolute_url(request, canonical_path)
    steps = []
    for step in GETTING_STARTED_SIMULATOR_STEPS:
        step_copy = dict(step)
        cta_slug = step_copy.get("cta_url_slug")
        step_copy["cta_url"] = (
            _setup_simulator_cta_url(request, cta_slug) if cta_slug else None
        )
        steps.append(step_copy)
    ctx = {
        **base_ctx,
        "seo_title": "Setup simulator | RunMyCampus",
        "seo_description": "Walk through the six steps from sign-up to launch. See what to expect and where to go next.",
        "canonical_url": canonical_url,
        "steps": steps,
        "active_nav_slug": "getting-started",
    }
    return render(request, "marketing/marketing_setup_simulator.html", ctx)


@require_GET
def compare_marketing_page(request, competitor_slug: str):
    """Compare RunMyCampus vs competitor: power-school, blackbaud, infinite-campus."""
    definition = COMPARE_PAGE_DEFINITIONS.get((competitor_slug or "").strip().lower())
    if not definition:
        raise Http404("Compare page not found")
    base_ctx = _marketing_base_context(request)
    canonical_path = f"/compare/{competitor_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    page_copy["slug"] = competitor_slug
    structured_data = _structured_data_for_page(
        page_type="WebPage",
        canonical_url=canonical_url,
        name=f"RunMyCampus vs {page_copy.get('competitor_name', competitor_slug)}",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )
    base_url = _absolute_url(request, "/").rstrip("/")
    breadcrumb_segments = [
        ("Home", "/"),
        ("Compare", "/compare/"),
        (page_copy.get("competitor_name", competitor_slug), canonical_path),
    ]
    breadcrumb_schema_json = json.dumps(
        _breadcrumb_list_schema(base_url, breadcrumb_segments)
    )
    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "breadcrumb_schema_json": breadcrumb_schema_json,
        "page": page_copy,
        "active_nav_slug": "compare",
    }
    return render(request, "marketing/marketing_compare_page.html", ctx)


DEVELOPER_PAGE_DEFINITIONS = {
    "api": {
        "label": "API",
        "seo_title": "RunMyCampus API - OpenAPI and REST",
        "seo_description": "REST API and OpenAPI schema for RunMyCampus integrations.",
        "headline": "API overview",
        "subheadline": "REST API and OpenAPI schema available at your school subdomain after login.",
        "sections": [
            {
                "title": "Schema",
                "body": "OpenAPI 3 schema at /api/schema/ui/ on your tenant subdomain.",
            },
            {
                "title": "Authentication",
                "body": "POST /api/auth/token/ with username/password; use Bearer token in Authorization header.",
            },
        ],
    },
    "webhooks": {
        "label": "Webhooks",
        "seo_title": "RunMyCampus Webhooks",
        "seo_description": "Webhook events and payloads for RunMyCampus integrations.",
        "headline": "Webhooks",
        "subheadline": "Subscribe to events and receive payloads at your endpoint.",
        "sections": [
            {
                "title": "Events",
                "body": "Subscribe to enrollment, grade, and billing events.",
            },
            {
                "title": "Delivery",
                "body": "Signed payloads and retry policy; configure in tenant settings.",
            },
        ],
    },
    "integrations": {
        "label": "Integrations",
        "seo_title": "RunMyCampus Integrations - Developers",
        "seo_description": "Build integrations with RunMyCampus: SIS, LMS, payments.",
        "headline": "Integrations",
        "subheadline": "Connect SIS, LMS, payment gateways, and identity providers.",
        "sections": [
            {
                "title": "LTI 1.3",
                "body": "LTI launch and deep linking; readiness at /api/interop/lti13/.",
            },
            {
                "title": "OneRoster",
                "body": "OneRoster API and CSV; readiness at /api/interop/oneroster/.",
            },
            {
                "title": "Ed-Fi & CEDS",
                "body": "Ed-Fi and CEDS endpoints for student and grade data.",
            },
        ],
    },
    "sdk": {
        "label": "SDK",
        "seo_title": "RunMyCampus SDK",
        "seo_description": "SDK and client libraries for RunMyCampus API.",
        "headline": "SDK",
        "subheadline": "Client libraries and auth helpers for API integration.",
        "sections": [
            {
                "title": "Repository",
                "body": "RunMyCampus SDK on GitHub: auth, base URL, and request helpers.",
            },
            {
                "title": "Sandbox",
                "body": "Try the sandbox at /developer-portal/sandbox/ for app preview.",
            },
        ],
    },
    "app-building": {
        "label": "App building",
        "seo_title": "Build Apps for RunMyCampus | Developer guide",
        "seo_description": "Build apps and extensions for the RunMyCampus marketplace. SDK, API, and sandbox.",
        "headline": "App building",
        "subheadline": "Build apps and extensions that run on RunMyCampus. Use the API, SDK, and sandbox.",
        "sections": [
            {
                "title": "Getting started",
                "body": "Register your app, get credentials, and use the API or SDK to build integrations.",
            },
            {
                "title": "Sandbox",
                "body": "Test your app in the developer sandbox at /developer-portal/sandbox/ before publishing.",
            },
            {
                "title": "Marketplace",
                "body": "Submit your app to the marketplace for schools to install. Governance and review pipeline.",
            },
        ],
    },
}

MARKETPLACE_PAGE_DEFINITIONS = {
    "": {
        "headline": "RunMyCampus Marketplace",
        "subheadline": "Apps, integrations, templates, blueprints, and policy packs to extend your platform.",
        "apps_copy": "Discover apps for admissions, academics, and operations.",
        "integrations_copy": "Connect LMS, payments, and identity providers.",
        "templates_copy": "Report templates, form templates, and branding templates.",
        "blueprints_copy": "Country and institution-type blueprints for faster setup.",
        "policy_packs_copy": "Pre-built policy bundles and compliance packs.",
        "partners_copy": "Built with our partners for education.",
    },
    "apps": {
        "headline": "Marketplace apps",
        "subheadline": "Apps to extend RunMyCampus.",
        "apps_copy": "Browse and install apps.",
        "integrations_copy": "",
        "templates_copy": "",
        "blueprints_copy": "",
        "policy_packs_copy": "",
        "partners_copy": "",
    },
    "integrations": {
        "headline": "Integrations",
        "subheadline": "Connect your systems.",
        "apps_copy": "",
        "integrations_copy": "LMS, SIS, payments, messaging.",
        "templates_copy": "",
        "blueprints_copy": "",
        "policy_packs_copy": "",
        "partners_copy": "",
    },
    "templates": {
        "headline": "Templates",
        "subheadline": "Report, form, and branding templates.",
        "apps_copy": "",
        "integrations_copy": "",
        "templates_copy": "Report templates, form templates, and dashboard layouts. Start from blueprints or customize.",
        "blueprints_copy": "",
        "policy_packs_copy": "",
        "partners_copy": "",
    },
    "blueprints": {
        "headline": "Blueprints",
        "subheadline": "Country and institution blueprints.",
        "apps_copy": "",
        "integrations_copy": "",
        "templates_copy": "",
        "blueprints_copy": "Pre-built policy and workflow bundles for faster setup and best practices. Country and institution-type blueprints.",
        "policy_packs_copy": "",
        "partners_copy": "",
    },
    "policy-packs": {
        "headline": "Policy packs",
        "subheadline": "Pre-built policy and compliance packs.",
        "apps_copy": "",
        "integrations_copy": "",
        "templates_copy": "",
        "blueprints_copy": "",
        "policy_packs_copy": "Policy bundles and compliance packs. Apply across tenants from the control plane.",
        "partners_copy": "",
    },
    "partners": {
        "headline": "Partners",
        "subheadline": "Built with our partners.",
        "apps_copy": "",
        "integrations_copy": "",
        "templates_copy": "",
        "blueprints_copy": "",
        "policy_packs_copy": "",
        "partners_copy": "Partner solutions and certified integrations.",
    },
}


@require_GET
def developer_marketing_page(request, section_slug: str):
    """Developer sub-pages: api, webhooks, integrations, sdk."""
    definition = DEVELOPER_PAGE_DEFINITIONS.get((section_slug or "").strip().lower())
    if not definition:
        raise Http404("Developer page not found")
    base_ctx = _marketing_base_context(request)
    canonical_path = f"/developers/{section_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    page_copy["slug"] = section_slug
    structured_data = _structured_data_for_page(
        page_type="WebPage",
        canonical_url=canonical_url,
        name=page_copy.get("label") or "RunMyCampus",
        description=page_copy.get("seo_description") or "",
        path=canonical_path,
    )
    ctx = {
        **base_ctx,
        "seo_title": page_copy.get("seo_title"),
        "seo_description": page_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "page": page_copy,
        "active_nav_slug": "solutions",
    }
    return render(request, "marketing/marketing_developer_page.html", ctx)


@require_GET
def marketplace_marketing_page(request, section: str = ""):
    """Marketplace landing and sections: apps, integrations, partners."""
    section_key = (section or "").strip().lower()
    definition = MARKETPLACE_PAGE_DEFINITIONS.get(
        section_key, MARKETPLACE_PAGE_DEFINITIONS.get("")
    )
    base_ctx = _marketing_base_context(request)
    if section_key:
        canonical_path = f"/marketplace/{section}/"
    else:
        canonical_path = "/marketplace/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(definition)
    page_copy["slug"] = section_key
    structured_data = _structured_data_for_page(
        page_type="WebPage",
        canonical_url=canonical_url,
        name=page_copy.get("headline", "Marketplace"),
        description=page_copy.get("subheadline", "RunMyCampus Marketplace."),
        path=canonical_path,
    )
    ctx = {
        **base_ctx,
        "seo_title": f"{page_copy.get('headline', 'Marketplace')} | RunMyCampus",
        "seo_description": page_copy.get("subheadline", "RunMyCampus Marketplace."),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "page": page_copy,
        "active_nav_slug": "solutions",
    }
    return render(request, "marketing/marketing_marketplace_page.html", ctx)


@require_GET
def regional_marketing_landing(request, country_code: str, language_code: str = "en"):
    """
    Regional landing page.
    Supported routes:
    - legacy: /cm/, /ca/
    - canonical: /<lang>/<country>/
    """
    normalized_country = _normalize_country_code(country_code)
    if not normalized_country:
        raise Http404("Region not found")
    ctx = _marketing_context(
        request,
        country_code=normalized_country,
        language_code=language_code or getattr(request, "LANGUAGE_CODE", "en"),
        regional=True,
    )
    return render(request, "schools/marketing_landing.html", ctx)


@require_GET
def marketing_robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {_absolute_url(request, '/sitemap.xml')}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def _sitemap_entries(request) -> list[tuple[str, str, str]]:
    """Return list of (loc, priority, changefreq) for marketing sitemap."""
    base = _absolute_url(request, "/").rstrip("/")
    path_specs: dict[str, tuple[str, str]] = {}  # path -> (priority, changefreq)

    path_specs["/"] = ("1.0", "weekly")
    path_specs["/education-operating-system/"] = ("0.95", "weekly")
    for platform_path in (
        "/platform/",
        "/platform/education-os/",
        "/platform/control-plane/",
        "/platform/marketplace/",
        "/platform/migration-cloud/",
        "/platform/runtime/",
        "/platform/integrations/",
        "/platform/security/",
        "/platform/analytics/",
        "/platform/student-information-system/",
        "/platform/admissions/",
        "/platform/attendance/",
        "/platform/fees-payments/",
        "/platform/grading-report-cards/",
        "/platform/parent-portal/",
        "/platform/teacher-portal/",
        "/platform/student-portal/",
        "/platform/communications/",
        "/platform/workflows/",
        "/platform/offline-first/",
    ):
        path_specs[platform_path] = ("0.85", "monthly")
    path_specs["/getting-started/"] = ("0.85", "monthly")
    path_specs["/getting-started/simulator/"] = ("0.75", "monthly")
    path_specs["/themes/"] = ("0.8", "monthly")
    path_specs["/design-studio/"] = ("0.8", "monthly")
    path_specs["/status/"] = ("0.75", "monthly")  # marketing trust page on public host
    path_specs["/uptime/"] = ("0.75", "monthly")  # alias for same page
    path_specs["/product-tour/"] = ("0.8", "monthly")
    path_specs["/resources/product-tour/"] = ("0.85", "monthly")
    path_specs["/migrate/simulator/"] = ("0.75", "monthly")
    path_specs["/migrate-from/"] = ("0.8", "monthly")
    path_specs["/research/"] = ("0.75", "monthly")
    path_specs["/reports/"] = ("0.75", "monthly")
    path_specs["/guides/"] = ("0.75", "monthly")
    for item in _marketing_nav():
        path = item["path"]
        if path in ("/pricing/", "/product/"):
            path_specs[path] = ("0.9", "weekly")
        else:
            path_specs[path] = ("0.8", "monthly")
    for item in _topical_nav():
        path_specs[item["path"]] = ("0.8", "monthly")
    path_specs["/discover/"] = ("0.8", "monthly")
    path_specs["/find/"] = ("0.8", "monthly")
    path_specs["/signup/"] = ("0.9", "weekly")
    path_specs["/book-demo/"] = ("0.9", "weekly")
    path_specs["/demo/"] = ("0.85", "weekly")
    path_specs["/company/"] = ("0.65", "monthly")
    path_specs["/contact/"] = ("0.75", "monthly")
    path_specs["/resources/help-center/"] = ("0.75", "monthly")
    path_specs["/marketing/"] = ("1.0", "weekly")
    path_specs["/cookie-policy/"] = ("0.5", "monthly")
    # Phase 3–4: institution, role, migrate, compare, trust, developers, marketplace
    for inst in (
        "k12",
        "universities",
        "technical-schools",
        "private-schools",
        "government-education",
        "international-schools",
        "faith-based-schools",
        "multi-campus",
        "growing-school-networks",
    ):
        path_specs[f"/solutions/{inst}/"] = ("0.8", "monthly")
    for role in (
        "school-admin",
        "teachers",
        "parents",
        "students",
        "it-directors",
        "government",
        "principals",
        "district-leaders",
        "finance",
    ):
        path_specs[f"/roles/{role}/"] = ("0.8", "monthly")
    path_specs["/for/principals/"] = ("0.75", "monthly")
    path_specs["/for/district-leaders/"] = ("0.75", "monthly")
    path_specs["/migrate/"] = ("0.8", "monthly")
    for src in (
        "from-power-school",
        "from-blackbaud",
        "from-infinite-campus",
        "from-veracross",
    ):
        path_specs[f"/migrate/{src}/"] = ("0.8", "monthly")
    for src in ("from-power-school", "from-blackbaud", "from-infinite-campus"):
        path_specs[f"/migrate-from/{src}/"] = ("0.75", "monthly")
    for comp in ("power-school", "blackbaud", "infinite-campus"):
        path_specs[f"/compare/{comp}/"] = ("0.8", "monthly")
    for trust_path in ("/security/", "/compliance/", "/ferpa/", "/gdpr/", "/lgpd/"):
        path_specs[trust_path] = ("0.7", "monthly")
    for dev in ("api", "webhooks", "integrations", "sdk", "app-building"):
        path_specs[f"/developers/{dev}/"] = ("0.7", "monthly")
    path_specs["/marketplace/"] = ("0.8", "monthly")
    path_specs["/marketplace/apps/"] = ("0.7", "monthly")
    path_specs["/marketplace/integrations/"] = ("0.7", "monthly")
    path_specs["/marketplace/templates/"] = ("0.7", "monthly")
    path_specs["/marketplace/blueprints/"] = ("0.7", "monthly")
    path_specs["/marketplace/policy-packs/"] = ("0.7", "monthly")
    path_specs["/marketplace/partners/"] = ("0.7", "monthly")
    for prod in (
        "admissions",
        "academics",
        "finance",
        "communication",
        "automation",
        "analytics",
    ):
        path_specs[f"/products/{prod}/"] = ("0.85", "monthly")
    for seo_slug in (
        "school-management-system",
        "student-information-system",
        "education-erp",
        "school-administration-software",
    ):
        path_specs[f"/{seo_slug}/"] = ("0.85", "monthly")

    try:
        from apps.brand_experience.models import GlobalBrandRegistry

        countries = list(
            GlobalBrandRegistry.objects.filter(is_active=True)
            .values_list("iso_code", "primary_language")
            .order_by("iso_code")
        )
    except (ImportError, DatabaseError, OperationalError, AttributeError, TypeError):
        countries = []

    if not countries:
        countries = [("CM", "fr"), ("CA", "en"), ("US", "en")]

    for iso_code, language in countries:
        code = (iso_code or "").strip().lower()
        lang = _normalize_language_code(language or "en")
        if not code:
            continue
        path_specs[f"/{lang}/{code}/"] = ("0.7", "monthly")

    return [
        (base + (p if p != "/" else "/"), prio, freq)
        for p, (prio, freq) in path_specs.items()
    ]


@require_GET
def marketing_sitemap_xml(request):
    """
    Lightweight sitemap for global marketing routes with priority and changefreq.
    """
    now = datetime.now(dt_timezone.utc).strftime("%Y-%m-%d")
    entries = _sitemap_entries(request)
    chunks = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, priority, changefreq in entries:
        chunks.append("  <url>")
        chunks.append(f"    <loc>{loc}</loc>")
        chunks.append(f"    <lastmod>{now}</lastmod>")
        chunks.append(f"    <priority>{priority}</priority>")
        chunks.append(f"    <changefreq>{changefreq}</changefreq>")
        chunks.append("  </url>")
    chunks.append("</urlset>")
    return HttpResponse("\n".join(chunks), content_type="application/xml")


@require_GET
def developer_hub(request):
    """
    Canonical /developer/ hub: OAuth, API v2 manifest, API Center, test console entry points.
    """
    base = request.build_absolute_uri("/").rstrip("/")
    base_ctx = _marketing_base_context(request)
    return render(
        request,
        "developer/hub.html",
        {
            **base_ctx,
            "page_slug": "developer-hub",
            "headline": "RunMyCampus for developers",
            "subheadline": "Register apps, connect APIs, and ship integrations safely.",
            "links": {
                "v2_manifest": f"{base}/api/v2/manifest.json",
                "v1_manifest": f"{base}/api/v1/manifest.json",
                "v2_ping": f"{base}/api/v2/ping/",
                "oauth_token": f"{base}/api/v1/oauth/token/",
                "oauth_authorize": f"{base}/api/v1/oauth/authorize/",
                "api_center": request.build_absolute_uri("/api-center/"),
                "developer_portal": request.build_absolute_uri(reverse("developer_portal")),
                "developer_console": request.build_absolute_uri(
                    reverse("developer_console")
                ),
                "sdk": request.build_absolute_uri(reverse("developer_sdk")),
                "sandbox": request.build_absolute_uri(reverse("developer_sandbox")),
                "public_api_docs": request.build_absolute_uri(
                    reverse("developer_public_api_docs")
                ),
                "admin_developer_applications": f"{base}/admin/apicenter/developerapplication/",
                "admin_marketplace_apps": f"{base}/admin/marketplace/marketplaceapp/",
                "admin_tenant_subscriptions": f"{base}/admin/billing/tenantsubscription/",
            },
        },
    )


@require_GET
def developer_console(request):
    """
    Developer console: app registration, versions, keys, webhooks, logs entry points.
    """
    base_ctx = _marketing_base_context(request)
    return render(
        request,
        "developer/console.html",
        {
            **base_ctx,
            "page_slug": "developer-console",
            "headline": "Developer console",
            "subheadline": "Register apps, ship semver versions, manage keys and webhooks.",
            "links": {
                "hub": request.build_absolute_uri(reverse("developer_hub")),
                "oauth_authorize": request.build_absolute_uri(
                    reverse("oauth:authorize")
                ),
                "oauth_token": request.build_absolute_uri(reverse("oauth:token")),
                "api_center": request.build_absolute_uri("/api-center/"),
                "integration_context": request.build_absolute_uri(
                    reverse("api_v1:platform-integration-context")
                ),
                "scoped_ping": request.build_absolute_uri(
                    reverse("api_v1:platform-scoped-ping")
                ),
                "public_api_docs": request.build_absolute_uri(
                    reverse("developer_public_api_docs")
                ),
            },
        },
    )


@require_GET
def developer_portal(request):
    """
    Developer portal (Section 6): API, webhooks, LTI/OneRoster, app lifecycle, SDK.
    Canonical on developer.runmycampus.com or /developer-portal/ on base.
    """
    base = get_canonical_base_domain() or request.get_host().split(":")[0]
    scheme = "https" if request.is_secure() else "http"
    # Interop and API schema live under tenant/school URL space; document paths.
    links = {
        "api_schema_path": "/api/schema/ui/",
        "api_schema_note": "Available after login at your school subdomain (e.g. yourschool.runmycampus.com/api/schema/ui/).",
        "interop_oneroster": request.build_absolute_uri("/api/interop/oneroster/"),
        "interop_lti13": request.build_absolute_uri("/api/interop/lti13/"),
        "interop_edfi": request.build_absolute_uri("/api/interop/edfi/"),
        "interop_ceds": request.build_absolute_uri("/api/interop/ceds/"),
        "webhooks_doc": f"{scheme}://docs.{base}/webhooks/"
        if base != "localhost"
        else request.build_absolute_uri("/docs/webhooks/"),
        "app_lifecycle_anchor": request.build_absolute_uri(
            reverse("developer_portal") + "#app-lifecycle"
        ),
        "sandbox": request.build_absolute_uri(reverse("developer_sandbox")),
        "sdk_repo": "https://github.com/runmycampus/sdk",
    }
    base_ctx = _marketing_base_context(request)
    return render(
        request,
        "schools/developer_portal.html",
        {
            **base_ctx,
            "page_slug": "developer-portal",
            "headline": "Developer Portal",
            "subheadline": "APIs, webhooks, LTI, OneRoster, and app extensions.",
            "links": links,
        },
    )


@require_GET
def developer_sdk(request):
    """
    SDK documentation page (Section 6): auth, base URL, and API reference pointers.
    """
    _base = get_canonical_base_domain() or request.get_host().split(":")[0]
    _scheme = "https" if request.is_secure() else "http"
    links = {
        "portal": request.build_absolute_uri(reverse("developer_portal")),
        "sandbox": request.build_absolute_uri(reverse("developer_sandbox")),
        "sdk_repo": "https://github.com/runmycampus/sdk",
        "api_schema_note": "After login at your school subdomain: /api/schema/ui/ for OpenAPI.",
        "auth_token": "POST /api/auth/token/ with username/password; use access token in Authorization: Bearer.",
        "auth_refresh": "POST /api/auth/token/refresh/ with refresh token.",
        "interop_edfi": "/api/interop/edfi/ (readiness); /api/interop/edfi/students/, .../studentSchoolAssociations/, .../grades/.",
        "interop_ceds": "/api/interop/ceds/ (readiness); /api/interop/ceds/students/, .../enrollments/, .../grades/.",
    }
    base_ctx = _marketing_base_context(request)
    return render(
        request,
        "schools/developer_sdk.html",
        {
            **base_ctx,
            "page_slug": "developer-sdk",
            "headline": "SDK & API reference",
            "subheadline": "Authentication, base URL, and API endpoints for RunMyCampus integrations.",
            "links": links,
        },
    )


@require_GET
def developer_public_api_docs(request):
    """Public developer API summary (§0.3); full detail in docs/DEVELOPER_PUBLIC_API.md."""
    base_ctx = _marketing_base_context(request)
    return render(
        request,
        "schools/developer_public_api_docs.html",
        {
            **base_ctx,
            "manifest_url": request.build_absolute_uri("/api/v1/manifest.json"),
            "schema_note": "/api/schema/ and /api/schema/ui/ after staff login on tenant host.",
        },
    )


@require_GET
def developer_sandbox(request):
    """
    App sandbox (Section 6): iframe container with CSP for third-party app preview.
    Sandbox attribute restricts script/origin; placeholder content for now.
    """
    html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Sandbox</title></head>
<body><p>App sandbox placeholder. Third-party apps run in an iframe with restricted permissions (CSP, sandbox attribute).</p></body></html>"""
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'self'"
    )
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response
