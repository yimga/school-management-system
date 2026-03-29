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
MARKETING_NAVBAR_VISIBLE_COUNT = 7


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
    """Primary marketing navbar: Product | Solutions | Pricing | Compare | Why Switch | Customers | Marketplace | Resources | Events | Company | [Login] [Start Free Trial]."""

    def p(name: str, fallback: str, **kwargs) -> str:
        u = _safe_reverse(name, kwargs=kwargs if kwargs else None)
        return u if u != "#" else fallback

    product_path = p("marketing_product", "/product/")
    product_children: list[dict] = [
        {"label": "Overview", "path": product_path},
        {
            "label": "Education OS",
            "path": p("marketing_education_operating_system", "/education-operating-system/"),
        },
        {"label": "Platform", "path": p("marketing_platform", "/platform/")},
        {"is_header": True, "label": "Product areas"},
        {
            "label": "Admissions",
            "path": p("marketing_products_admissions", "/products/admissions/"),
        },
        {
            "label": "Academics",
            "path": p("marketing_products_academics", "/products/academics/"),
        },
        {"label": "Finance", "path": p("marketing_products_finance", "/products/finance/")},
        {
            "label": "Communication",
            "path": p("marketing_products_communication", "/products/communication/"),
        },
        {
            "label": "Automation",
            "path": p("marketing_products_automation", "/products/automation/"),
        },
        {
            "label": "Analytics",
            "path": p("marketing_products_analytics", "/products/analytics/"),
        },
    ]

    solutions_path = p("marketing_solutions", "/solutions/")
    solutions_children: list[dict] = [
        {"label": "Solutions overview", "path": solutions_path},
        {"is_header": True, "label": "Use cases"},
    ]
    for slug, topic in sorted(
        TOPICAL_LANDING_DEFINITIONS.items(),
        key=lambda x: (x[1].get("label") or x[0]).lower(),
    ):
        solutions_children.append(
            {
                "label": topic.get("label") or slug.replace("-", " ").title(),
                "path": p(
                    "marketing_topic",
                    f"/solutions/{slug}/",
                    topic_slug=slug,
                ),
            }
        )
    solutions_children.append({"is_header": True, "label": "Institutions"})
    _inst_fallback = {
        "institution_k12": "/solutions/k12/",
        "institution_universities": "/solutions/universities/",
        "institution_technical_schools": "/solutions/technical-schools/",
        "institution_private_schools": "/solutions/private-schools/",
        "institution_government_education": "/solutions/government-education/",
    }
    for url_name, label in (
        ("institution_k12", "K-12"),
        ("institution_universities", "Universities"),
        ("institution_technical_schools", "Technical schools"),
        ("institution_private_schools", "Private schools"),
        ("institution_government_education", "Government education"),
    ):
        solutions_children.append(
            {
                "label": label,
                "path": p(url_name, _inst_fallback[url_name]),
            }
        )

    return [
        {
            "label": "Product",
            "path": product_path,
            "children": product_children,
        },
        {
            "label": "Solutions",
            "path": solutions_path,
            "children": solutions_children,
        },
        {"label": "Pricing", "path": p("marketing_pricing", "/pricing/")},
        {"label": "Compare", "path": p("marketing_compare", "/compare/")},
        {
            "label": "Why Switch",
            "path": p("marketing_why_switch", "/why-switch/"),
        },
        {
            "label": "Customers",
            "path": p("marketing_case_studies", "/case-studies/"),
        },
        {
            "label": "Marketplace",
            "path": p("marketing_app_marketplace", "/app-marketplace/"),
        },
        {
            "label": "Resources",
            "path": p("marketing_resources", "/resources/"),
        },
        {"label": "Events", "path": p("marketing_events", "/events/")},
        {
            "label": "10 Reasons",
            "path": p("marketing_10_reasons", "/10-reasons/"),
        },
        {"label": "Company", "path": p("marketing_about", "/about/")},
    ]


def _topical_nav() -> list[dict]:
    return [
        {"slug": slug, "label": topic["label"], "path": f"/solutions/{slug}/"}
        for slug, topic in TOPICAL_LANDING_DEFINITIONS.items()
    ]


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
        "seo_title": seo.get("seo_title") or "RunMyCampus - Global School Operations",
        "seo_description": seo.get("seo_description")
        or "Tenant-first school platform for academics, finance, and operations.",
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
            "cta_primary": "Démarrer l'essai gratuit",
            "proof_lead": "Adapté aux écoles francophones et au contexte local.",
        },
        "CA": {
            "cta_primary": "Start free trial",
            "proof_lead": "Built for Canadian schools and multi-province deployments.",
        },
        "NG": {
            "cta_primary": "Start free trial",
            "proof_lead": "Designed for Nigerian schools and WAEC alignment.",
        },
        "GB": {
            "cta_primary": "Start free trial",
            "proof_lead": "UK term structures and British curriculum support.",
        },
    }
    return variants.get(
        country,
        {
            "cta_primary": "Start free trial",
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
        "Regional compliance defaults",
        "Subdomain tenant isolation",
        "Cross-subdomain auth support",
        "Localized terminology and labels",
        "Manager command workflows",
        "API and documentation host split",
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
            "value": "3",
            "label": "dedicated surfaces",
            "detail": "Public, tenant, and manager host separation.",
        },
        {
            "value": "195+",
            "label": "country-ready profiles",
            "detail": "Registry-driven localization and defaults.",
        },
        {
            "value": "24/7",
            "label": "operator readiness",
            "detail": "Support and governance from manager workflows.",
        },
        {
            "value": "100%",
            "label": "subdomain tenancy",
            "detail": "Strict isolation for tenant security boundaries.",
        },
    ]
    # Wave 2: localized proof cards for country-language landing variants
    _proof_by_country = {
        "CM": [
            {
                "value": "3",
                "label": "surfaces dédiées",
                "detail": "Séparation public, tenant et manager.",
            },
            {
                "value": "195+",
                "label": "pays pris en charge",
                "detail": "Localisation et conformité par région.",
            },
            {
                "value": "24/7",
                "label": "disponibilité opérationnelle",
                "detail": "Support et gouvernance depuis le manager.",
            },
            {
                "value": "100%",
                "label": "tenance par sous-domaine",
                "detail": "Isolation stricte par école.",
            },
        ],
        "CA": [
            {
                "value": "3",
                "label": "dedicated surfaces",
                "detail": "Public, tenant, and manager host separation.",
            },
            {
                "value": "195+",
                "label": "country-ready profiles",
                "detail": "Registry-driven localization and defaults.",
            },
            {
                "value": "24/7",
                "label": "operator readiness",
                "detail": "Support and governance from manager workflows.",
            },
            {
                "value": "100%",
                "label": "subdomain tenancy",
                "detail": "Strict isolation for tenant security boundaries.",
            },
        ],
        "NG": [
            {
                "value": "3",
                "label": "dedicated surfaces",
                "detail": "Public, tenant, and manager host separation.",
            },
            {
                "value": "195+",
                "label": "country-ready profiles",
                "detail": "Registry-driven localization and defaults.",
            },
            {
                "value": "24/7",
                "label": "operator readiness",
                "detail": "Support and governance from manager workflows.",
            },
            {
                "value": "100%",
                "label": "subdomain tenancy",
                "detail": "Strict isolation for tenant security boundaries.",
            },
        ],
        "GB": [
            {
                "value": "3",
                "label": "dedicated surfaces",
                "detail": "Public, tenant, and manager host separation.",
            },
            {
                "value": "195+",
                "label": "country-ready profiles",
                "detail": "Registry-driven localization and defaults.",
            },
            {
                "value": "24/7",
                "label": "operator readiness",
                "detail": "Support and governance from manager workflows.",
            },
            {
                "value": "100%",
                "label": "subdomain tenancy",
                "detail": "Strict isolation for tenant security boundaries.",
            },
        ],
    }
    # Use localized proof stats when country matches (regional or geo-personalized main landing)
    if country in _proof_by_country:
        proof_stats = _proof_by_country[country]

    institution_logos = [
        "Greenfield Academy",
        "Nile Valley Schools",
        "Toronto Scholars Group",
        "Douala Science Institute",
        "Kampala Future Leaders",
        "Maple Heights College",
        "Blue Coast International",
        "Riverside Preparatory",
    ]
    _logos_by_country = {
        "CM": [
            "Institut des Sciences Douala",
            "Lycée Bilingue",
            "École Greenfield",
            "Réseau Nile Valley",
            "Académie Maple",
            "Campus Riverside",
        ],
        "CA": [
            "Toronto Scholars Group",
            "Maple Heights College",
            "Blue Coast International",
            "Riverside Preparatory",
            "Nile Valley Schools",
            "Greenfield Academy",
        ],
    }
    if regional and country in _logos_by_country:
        institution_logos = _logos_by_country[country]

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
            "tagline": "For single-campus schools",
            "highlights": [
                "Admissions and enrollment core",
                "Academics, attendance, and reports",
                "Parent, teacher, and student portals",
            ],
            "cta_label": "Start free trial",
            "cta_path": _safe_reverse("signup_school"),
        },
        {
            "plan": "Growth",
            "tagline": "For expanding school networks",
            "highlights": [
                "Multi-campus governance",
                "Regional branding and localization",
                "Support workflow and SLA visibility",
            ],
            "cta_label": "View pricing",
            "cta_path": "/pricing/",
        },
        {
            "plan": "Enterprise White-label",
            "tagline": "For operators at national scale",
            "highlights": [
                "Dedicated manager operations",
                "Advanced API and integration controls",
                "Compliance and audit governance",
            ],
            "cta_label": "Book architecture call",
            "cta_path": "/book-demo/",
        },
    ]

    trust_controls = [
        "FERPA and GDPR aligned workflows",
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
            "title": "24/7 support",
            "body": (
                "Operator-run infrastructure with escalation paths for schools across "
                "time zones."
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
        "Scalable Architecture",
        "24/7 Global Support",
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

    # Outcome-focused landing copy (world-class SaaS front). Wave 4: evidence-driven by geo and channel.
    # Education Operating System narrative: headline and subtext align with Platform Visual Architecture.
    hero_headline = "The Operating System for Modern Schools"
    hero_subheadline = "Admissions, academics, finance, communication, analytics, and governance — unified in one platform."
    _hero_by_country = {
        "CM": {
            "headline": "La plateforme pour les établissements scolaires modernes.",
            "subheadline": "Admissions, académique, finance, communication et conformité dans une seule plateforme. Gérez votre campus avec clarté.",
        },
        "CA": {
            "headline": "The Global Operating System for Education",
            "subheadline": "One platform for admissions, academics, finance, and compliance. Trusted by schools across Canada and beyond.",
        },
        "NG": {
            "headline": "The Global Operating System for Education",
            "subheadline": "One platform for admissions, academics, finance, and compliance. Trusted by schools across Nigeria and Africa.",
        },
        "GB": {
            "headline": "The Global Operating System for Education",
            "subheadline": "One platform for admissions, academics, finance, and compliance. Trusted by schools across the UK and beyond.",
        },
    }
    _hero_by_channel = {
        "google": {
            "headline": "The Global Operating System for Education",
            "subheadline": "One platform for admissions, academics, finance, and compliance. Try free—no credit card required.",
        },
        "linkedin": {
            "headline": "School operations, unified.",
            "subheadline": "For education leaders: admissions, finance, compliance, and reporting in one platform. Scale without sprawl.",
        },
        "facebook": {
            "headline": "Run your school on one platform.",
            "subheadline": "Admissions, finance, and compliance in one place. Start free—no credit card required.",
        },
        "newsletter": {
            "headline": "The Global Operating System for Education",
            "subheadline": "For subscribers: one platform for admissions, academics, finance, and compliance. Book a demo or start free.",
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
    _education_os_path = (
        _safe_reverse("marketing_education_operating_system")
        or "/education-operating-system/"
    )
    _signup = _safe_reverse("signup_school")
    _book_demo = _safe_reverse("marketing_book_demo") or "/book-demo/"
    _login = _safe_reverse("global_login_discovery")
    # A/B: marketing_cta_variant "secondary" emphasizes demo before trial (session-sticky).
    if marketing_cta_variant == "secondary":
        hero_ctas = [
            {
                "label": "Book a Demo",
                "url": _book_demo,
                "primary": True,
            },
            {
                "label": "Start Free Trial",
                "url": _signup,
                "primary": False,
            },
            {"label": "See How It Works", "url": _education_os_path, "primary": False},
            {"label": "Login", "url": _login, "primary": False},
        ]
    else:
        hero_ctas = [
            {
                "label": "Start Free Trial",
                "url": _signup,
                "primary": True,
            },
            {
                "label": "Book a Demo",
                "url": _book_demo,
                "primary": False,
            },
            {"label": "See How It Works", "url": _education_os_path, "primary": False},
            {"label": "Login", "url": _login, "primary": False},
        ]
    _trust_placeholder = static("images/marketing/logo-placeholder.svg")
    trust_logos = [
        {"name": "School Trust", "image_url": _trust_placeholder},
        {"name": "Edu Partners", "image_url": _trust_placeholder},
        {"name": "Global Schools", "image_url": _trust_placeholder},
    ]
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
        "195+ country-ready profiles, multi-currency, data residency."
    )
    three_key_features = [
        "AI Co-pilot",
        "Real-time Analytics",
        "Customizable Workflows",
    ]
    migration_bullets = [
        "Import students, staff, and historical data from spreadsheets or legacy systems.",
        "Map your existing workflows to RunMyCampus modules with guided setup.",
        "Scales globally: " + scales_globally_line,
        "Go live with phased rollout and dedicated support during migration.",
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
        hero_dashboard_image_url = static("images/marketing/hero-placeholder.svg")
    # 9.5 proof-rich marketing: key for asset governance (style guide, versioning, approval).
    proof_hero_image_key = (
        getattr(settings, "MARKETING_PROOF_HERO_IMAGE_KEY", None) or "hero_dashboard"
    )
    # Default hero video: Blender Foundation sample (MP4) when env/AI unset — real <source>, not empty.
    _default_hero_sample_mp4 = (
        "https://download.blender.org/peach/bigbuckbunny_movies/BigBuckBunny_320x180.mp4"
    )
    _ai_video = get_marketing_ai_asset_url("hero_video")
    _settings_video = getattr(settings, "MARKETING_HERO_VIDEO_URL", None)
    if _ai_video:
        hero_video_url = _ai_video
    elif _settings_video is not None:
        # Explicit "" in settings → static hero image only (no <video>).
        hero_video_url = (_settings_video or "").strip()
    else:
        hero_video_url = _default_hero_sample_mp4
    hero_video_poster_url = (
        getattr(settings, "MARKETING_HERO_VIDEO_POSTER_URL", None)
        or hero_dashboard_image_url
        or ""
    )
    product_demo_image_url = (
        getattr(settings, "MARKETING_PRODUCT_DEMO_IMAGE_URL", None)
        or getattr(settings, "MARKETING_HERO_IMAGE_URL", None)
        or hero_dashboard_image_url
        or static("images/marketing/hero-placeholder.svg")
    )
    # Product visualization strip: 5 slides required (Batch 1 — admin, teacher, parent, student, analytics).
    # Proof-rich §8.4: every slide has non-empty image_static when image_url missing so section never shows empty frames.
    _proof_viz_fallback = "images/marketing/platform-diagram-marketing.svg"
    product_visualization_slides = getattr(
        settings, "MARKETING_PRODUCT_VISUALIZATION_SLIDES", None
    ) or [
        {
            "title": "Admin dashboard",
            "caption": "Real-time enrollment, finance, and compliance dashboards.",
            "image_url": "",
            "image_static": "images/marketing/viz-admin.svg",
        },
        {
            "title": "Teacher dashboard",
            "caption": "Grades, attendance, and class tools in one place.",
            "image_url": "",
            "image_static": "images/marketing/viz-teacher.svg",
        },
        {
            "title": "Parent portal",
            "caption": "One place for your children: attendance, grades, and school updates.",
            "image_url": "",
            "image_static": "images/marketing/viz-student360.svg",
        },
        {
            "title": "Student 360",
            "caption": "One view per student: attendance, grades, interventions.",
            "image_url": "",
            "image_static": "images/marketing/viz-student360.svg",
        },
        {
            "title": "Admin analytics",
            "caption": "Operational intelligence and reporting at a glance.",
            "image_url": "",
            "image_static": "images/marketing/viz-admin.svg",
        },
    ]
    for slide in product_visualization_slides:
        if not slide.get("image_url") and not slide.get("image_static"):
            slide["image_static"] = _proof_viz_fallback
    _ecosystem_icon = static("images/marketing/logo-placeholder.svg")
    _marketplace_path = (
        _safe_reverse("marketing_app_marketplace") or "/app-marketplace/"
    )
    _integrations_path = _safe_reverse("marketing_integrations") or "/integrations/"
    ecosystem_apps = [
        {
            "name": "LMS / LTI",
            "summary": "Connect your learning management system.",
            "image_url": _ecosystem_icon,
            "install_path": _marketplace_path,
            "cta_path": _marketplace_path,
            "cta_label": "Explore",
        },
        {
            "name": "Payment gateways",
            "summary": "Stripe, PayPal, and local providers.",
            "image_url": _ecosystem_icon,
            "install_path": _integrations_path,
            "cta_path": _integrations_path,
            "cta_label": "View integrations",
        },
        {
            "name": "Messaging",
            "summary": "SMS and email providers for notifications.",
            "image_url": _ecosystem_icon,
            "install_path": _integrations_path,
            "cta_path": _integrations_path,
            "cta_label": "View integrations",
        },
        {
            "name": "Single sign-on",
            "summary": "SAML and OAuth for enterprise identity.",
            "image_url": _ecosystem_icon,
            "install_path": _integrations_path,
            "cta_path": _integrations_path,
            "cta_label": "View integrations",
        },
    ]
    testimonials = [
        {
            "quote": "We moved from spreadsheets to RunMyCampus in one term. Admissions and billing are finally in one place.",
            "author": "Sarah M.",
            "role": "Operations Director, Greenfield Academy",
            "stars": 5,
        },
        {
            "quote": "Multi-campus visibility without losing each school's identity. Exactly what we needed.",
            "author": "James K.",
            "role": "Network Lead, Nile Valley Schools",
            "stars": 5,
        },
        {
            "quote": "Compliance and reporting used to take days. Now we have dashboards and exports in minutes.",
            "author": "Priya L.",
            "role": "Finance & Compliance, Toronto Scholars",
            "stars": 5,
        },
    ]
    # Video testimonials: list of {url, title, thumbnail_url}; override via MARKETING_VIDEO_TESTIMONIALS when ready
    _video_testimonials_setting = getattr(
        settings, "MARKETING_VIDEO_TESTIMONIALS", None
    )
    if _video_testimonials_setting:
        video_testimonials = _video_testimonials_setting
    else:
        # Seeded placeholders: external watch links + local SVG thumbs (no hotlinked images in tests).
        _vthumb_a = static("images/marketing/testimonial-thumb.svg")
        _vthumb_b = static("images/marketing/illustration-students.svg")
        video_testimonials = [
            {
                "url": "https://www.youtube.com/watch?v=YE7VzlLtp-4",
                "title": "Platform walkthrough (sample)",
                "thumbnail_url": _vthumb_a,
            },
            {
                "url": "https://www.youtube.com/watch?v=eRsGyueBVvA",
                "title": "Migration and go-live (sample)",
                "thumbnail_url": _vthumb_b,
            },
        ]
    security_badges = [
        "FERPA aligned",
        "GDPR ready",
        "SOC 2 roadmap",
        "Encryption at rest & in transit",
        "Role-based access",
    ]
    final_cta_headline = "Ready to run your campus with one platform?"

    # Phase 2: Institutional coverage (section 2) – K-12, Universities, Technical, Private, Government
    institution_types = [
        {
            "label": "K-12",
            "summary": "Elementary and secondary schools with enrollment, grades, and parent engagement.",
            "path": "/solutions/",
        },
        {
            "label": "Universities",
            "summary": "Higher ed admissions, academic structure, and multi-campus governance.",
            "path": "/solutions/",
        },
        {
            "label": "Technical schools",
            "summary": "Career and technical education with certification and placement tracking.",
            "path": "/solutions/",
        },
        {
            "label": "Private schools",
            "summary": "Independent and faith-based schools with full operations and fundraising.",
            "path": "/solutions/",
        },
        {
            "label": "Government education",
            "summary": "Public sector and government-run institutions with compliance and reporting.",
            "path": "/solutions/",
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
            "body": "Billing cycles, payment gateways, and financial reporting without spreadsheets.",
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

    # Non-negotiables: platform narrative (six pillars from RunMyCampus_Platform_Visual_Architecture)
    platform_headline = "The Operating System for Modern Schools"
    category_claim = "The Operating System for Modern Education."
    platform_pillar_grid = [
        {"label": "Education OS", "sub": "One platform for running the entire school."},
        {"label": "Control Plane", "sub": "Manage schools, districts, and networks."},
        {
            "label": "Marketplace",
            "sub": "Extend the platform with apps and integrations.",
        },
        {"label": "Migration Cloud", "sub": "Switch from legacy systems safely."},
        {
            "label": "Tenant Runtime",
            "sub": "One platform core, configured for your institution.",
        },
        {
            "label": "Analytics & Integrations",
            "sub": "See what matters and connect what you use.",
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

    # Non-negotiables: social proof & scale
    by_the_numbers = [
        {"value": "195+", "label": "countries"},
        {"value": "99.9%", "label": "uptime target"},
        {"value": "1", "label": "platform"},
    ]
    # Outcome metrics for data viz (e.g. case study outcomes); optional bar_pct for mini chart (0-100)
    outcome_metrics = getattr(settings, "MARKETING_OUTCOME_METRICS", None) or [
        {
            "value": "40%",
            "label": "less admin workload",
            "detail": "Schools report reduced time on manual processes.",
            "bar_pct": 40,
        },
        {
            "value": "2×",
            "label": "faster admissions",
            "detail": "From application to decision in half the time.",
            "bar_pct": 50,
        },
    ]
    _logo_placeholder = static("images/marketing/logo-placeholder.svg")
    customer_logos = [
        {"name": "Greenfield Academy", "logo_url": _logo_placeholder},
        {"name": "Nile Valley Schools", "logo_url": _logo_placeholder},
        {"name": "Toronto Scholars", "logo_url": _logo_placeholder},
        {"name": "Lagos STEM College", "logo_url": _logo_placeholder},
        {"name": "Pacific Ridge Academy", "logo_url": _logo_placeholder},
        {"name": "Heritage International", "logo_url": _logo_placeholder},
        {"name": "Summit Prep Network", "logo_url": _logo_placeholder},
        {"name": "Riverside Charter Trust", "logo_url": _logo_placeholder},
    ]
    awards_recognition = [
        "FERPA aligned",
        "GDPR ready",
        "SOC 2 roadmap",
    ]
    review_badges = [
        {
            "name": "Capterra",
            "url": "https://www.capterra.com/school-administration-software/",
            "stars": "4.8",
            "reviews": "50+",
        },
        {
            "name": "G2",
            "url": "https://www.g2.com/categories/education/school-management",
            "stars": "4.7",
            "reviews": "30+",
        },
    ]
    ten_reasons_page_path = _safe_reverse("marketing_10_reasons") or "/10-reasons/"

    # Non-negotiables: discovery (role + challenge)
    for_your_role = [
        {
            "label": "Principal",
            "path": _safe_reverse("marketing_solutions") or "/solutions/",
            "summary": "Visibility and control across your school.",
        },
        {
            "label": "Admin",
            "path": _safe_reverse("role_school_admin") or "/roles/school-admin/",
            "summary": "Day-to-day operations in one place.",
        },
        {
            "label": "Finance",
            "path": _safe_reverse("marketing_pricing") or "/pricing/",
            "summary": "Billing, fees, and reporting.",
        },
        {
            "label": "IT",
            "path": _safe_reverse("role_it_directors") or "/roles/it-directors/",
            "summary": "Integrations, security, and provisioning.",
        },
        {
            "label": "Teacher",
            "path": _safe_reverse("role_teachers") or "/roles/teachers/",
            "summary": "Grades, attendance, and class tools.",
        },
        {
            "label": "Parent",
            "path": _safe_reverse("role_parents") or "/roles/parents/",
            "summary": "One portal for your children.",
        },
        {
            "label": "Operator",
            "path": _safe_reverse("marketing_app_marketplace") or "/app-marketplace/",
            "summary": "Multi-tenant command center.",
        },
    ]
    solve_by_challenge = [
        {
            "title": "Reduce admin burden",
            "path": _safe_reverse("marketing_product") or "/product/",
        },
        {
            "title": "Multi-campus visibility",
            "path": _safe_reverse("marketing_case_studies") or "/case-studies/",
        },
        {
            "title": "Parent engagement",
            "path": _safe_reverse("marketing_solutions") or "/solutions/",
        },
        {
            "title": "Migration from spreadsheets",
            "path": _safe_reverse("migrate_marketing_page") or "/migrate/",
        },
        {
            "title": "Compliance without the headache",
            "path": _safe_reverse("marketing_security_compliance")
            or "/security-compliance/",
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

    # Non-negotiables: product pillars (6) + AI + differentiation; link to deep product pages when available
    product_pillars_home = [
        {
            "title": "Admissions & Enrollment",
            "summary": "Capture leads, track applications, onboard students.",
            "path": _safe_reverse("marketing_products_admissions")
            or "/products/admissions/",
        },
        {
            "title": "Academics & Grades",
            "summary": "Syllabi, attendance, report cards, interventions.",
            "path": _safe_reverse("marketing_products_academics")
            or "/products/academics/",
        },
        {
            "title": "Finance & Billing",
            "summary": "Fees, payments, financial reporting.",
            "path": _safe_reverse("marketing_products_finance") or "/products/finance/",
        },
        {
            "title": "Communication",
            "summary": "Role-ready portals for parents, teachers, students.",
            "path": _safe_reverse("marketing_products_communication")
            or "/products/communication/",
        },
        {
            "title": "Compliance & Reporting",
            "summary": "Audit trails, regional compliance, export-ready reports.",
            "path": _safe_reverse("marketing_security_compliance")
            or "/security-compliance/",
        },
        {
            "title": "Manager / Operations",
            "summary": "Super-admin command center for multi-tenant operators.",
            "path": _safe_reverse("marketing_app_marketplace") or "/app-marketplace/",
        },
    ]
    hero_ai_line = "One platform for admissions, academics, finance, and compliance—with AI that helps your team save time."
    differentiation_block = [
        "Multi-tenant from day one: each school gets its own domain, branding, and data.",
        "Operator layer: one control plane for many campuses.",
        "Global-first: multi-currency, multi-language, multi-timezone, country-specific grading.",
        "One product: no feature sprawl—admissions, academics, finance, communication, compliance in one place.",
    ]

    # Enterprise path
    enterprise_path_copy = "For operators at national scale. Book an architecture call for dedicated governance, compliance posture, and white-label branding."

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
            "role": "principal",
            "label": "Principal",
            "image_url": "",
            "image_static": "images/marketing/viz-admin.svg",
        },
        {
            "role": "teacher",
            "label": "Teacher",
            "image_url": "",
            "image_static": "images/marketing/viz-teacher.svg",
        },
        {
            "role": "parent",
            "label": "Parent",
            "image_url": "",
            "image_static": "images/marketing/viz-student360.svg",
        },
        {
            "role": "student",
            "label": "Student",
            "image_url": "",
            "image_static": "images/marketing/viz-student360.svg",
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
        "topical_nav": _topical_nav(),
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
        "marketing_analytics_preconnect_origin": marketing_analytics_preconnect_origin,
        "SHOW_HEADER_CONTEXT_STRIP": False,
        # Landing revamp: outcome-focused copy and 10-section context
        "marketing_navbar_primary": (nav_primary := _marketing_navbar_primary()),
        "marketing_navbar_visible_count": MARKETING_NAVBAR_VISIBLE_COUNT,
        "marketing_navbar_has_more": len(nav_primary) > MARKETING_NAVBAR_VISIBLE_COUNT,
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
            {"label": "Countries", "value": "195+"},
            {"label": "Currencies", "value": "Multi-currency"},
            {"label": "Languages", "value": "Multi-language"},
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
            {"label": "Admissions", "detail": "One application record"},
            {"label": "Roster", "detail": "Class placement in sync"},
            {"label": "Finance", "detail": "Invoices tied to the same student"},
        ],
        "marketing_apac_story": {
            "headline": "Asia–Pacific momentum",
            "body": (
                "Government digitization and private-school growth are accelerating education software adoption "
                "across APAC. RunMyCampus ships multi-tenant, multi-currency, and locale-aware operations "
                "so regional schools can launch without re-architecting later."
            ),
            "citations_note": (
                "Analysts consistently rank Asia–Pacific among the fastest-growing regions for EdTech and "
                "school management software (see sector reports from Grand View Research, Mordor Intelligence, "
                "and comparable market research)."
            ),
        },
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
    loaded = _load_marketing_page_from_file(normalized_slug)
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

    blog_posts = _get_blog_posts() if page_slug == "blog" else []
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
    return render(request, "schools/marketing_page.html", ctx)


@require_POST
@csrf_protect
def submit_demo_request(request):
    """
    Accept book-a-demo form POST (name, email, school, message).
    If MARKETING_DEMO_WEBHOOK_URL is set, POST JSON to it; then redirect to book-demo with ?submitted=1 or ?error=1.
    """
    name = (request.POST.get("name") or "").strip()[:256]
    email = (request.POST.get("email") or "").strip()[:256]
    school = (request.POST.get("school") or "").strip()[:256]
    message = (request.POST.get("message") or "").strip()[:2000]
    webhook_url = getattr(settings, "MARKETING_DEMO_WEBHOOK_URL", None) or ""
    success = False
    if webhook_url and email:
        payload = json.dumps(
            {
                "name": name,
                "email": email,
                "school": school,
                "message": message,
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
    redirect_url = reverse("marketing_book_demo")
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
    """Wave 4: Conversion funnel dashboard (visit -> discovery -> signup -> activation). Staff only."""
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
            signup=Count("id", filter=Q(event_type="signup")),
            activation=Count("id", filter=Q(event_type="activation")),
        )
        .order_by("-visit")
    )
    channel_breakdown = [
        {
            "utm_source": r.get("utm_source") or "",
            "utm_medium": r.get("utm_medium") or "",
            "visit": r.get("visit", 0),
            "discovery": r.get("discovery", 0),
            "signup": r.get("signup", 0),
            "activation": r.get("activation", 0),
        }
        for r in channel_qs
    ]

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
        "book-demo": "marketing_book_demo",
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
    ):
        path_specs[platform_path] = ("0.85", "monthly")
    path_specs["/getting-started/"] = ("0.85", "monthly")
    path_specs["/getting-started/simulator/"] = ("0.75", "monthly")
    path_specs["/themes/"] = ("0.8", "monthly")
    path_specs["/design-studio/"] = ("0.8", "monthly")
    path_specs["/status/"] = ("0.75", "monthly")  # marketing trust page on public host
    path_specs["/uptime/"] = ("0.75", "monthly")  # alias for same page
    path_specs["/product-tour/"] = ("0.8", "monthly")
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
    path_specs["/cookie-policy/"] = ("0.5", "monthly")
    # Phase 3–4: institution, role, migrate, compare, trust, developers, marketplace
    for inst in (
        "k12",
        "universities",
        "technical-schools",
        "private-schools",
        "government-education",
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
