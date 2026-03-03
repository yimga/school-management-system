"""
RunMyCampus marketing and SEO endpoints.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET

from apps.schools.host_routing import get_canonical_base_domain
from apps.siteconfig.brand_registry import resolve_global_brand_context
from apps.siteconfig.global_catalog import GlobalGeoCatalog


MARKETING_PAGE_DEFINITIONS = {
    "product": {
        "label": "Product",
        "seo_title": "RunMyCampus Product - Unified school operations platform",
        "seo_description": "One platform for admissions, academics, finance, communication, and compliance across every campus.",
        "headline": "One operating system for every school workflow.",
        "subheadline": "Run admissions, academics, billing, communication, and compliance from a single tenant-first platform.",
        "schema_type": "SoftwareApplication",
        "segments": [
            {
                "title": "Unified data model",
                "body": "Students, staff, payments, reports, and interventions share one source of truth.",
            },
            {
                "title": "Role-ready portals",
                "body": "School admins, teachers, parents, and students get purpose-built workflows.",
            },
            {
                "title": "Global tenancy",
                "body": "Operate one campus or many with domain, policy, and branding isolation.",
            },
        ],
    },
    "solutions": {
        "label": "Solutions",
        "seo_title": "RunMyCampus Solutions - K12, multi-campus, and private schools",
        "seo_description": "Purpose-built deployment patterns for private schools, district networks, and multi-campus operators.",
        "headline": "Solutions aligned to your school model.",
        "subheadline": "Deploy fast with templates for private schools, district groups, and multi-entity education organizations.",
        "schema_type": "CollectionPage",
        "segments": [
            {
                "title": "Single-campus schools",
                "body": "Launch quickly with ready workflows for onboarding, grading, fee management, and reporting.",
            },
            {
                "title": "Multi-campus networks",
                "body": "Standardize operations while preserving campus-level autonomy and identity.",
            },
            {
                "title": "Regional operators",
                "body": "Use localization controls for language, compliance profiles, terms, and grading systems.",
            },
        ],
    },
    "pricing": {
        "label": "Pricing",
        "seo_title": "RunMyCampus Pricing - Transparent plans for growing schools",
        "seo_description": "Transparent school management pricing with plan tiers, add-ons, and enterprise deployment options.",
        "headline": "Pricing that scales with your campus.",
        "subheadline": "Choose a plan by operating model, unlock add-ons, and keep billing visibility across every tenant.",
        "schema_type": "OfferCatalog",
        "segments": [
            {
                "title": "Plan clarity",
                "body": "Map plans to usage, student volume, and feature needs without hidden complexity.",
            },
            {
                "title": "Add-on flexibility",
                "body": "Enable advanced modules as your school grows, from integrations to analytics.",
            },
            {
                "title": "Super-admin oversight",
                "body": "Track trial status, usage, and billing posture in one command center.",
            },
        ],
    },
    "compare": {
        "label": "Compare",
        "seo_title": "RunMyCampus Compare - Evaluate school management alternatives",
        "seo_description": "Compare tenant architecture, admin controls, and parent/teacher experience before choosing your platform.",
        "headline": "Compare on architecture, not just feature count.",
        "subheadline": "Use objective criteria to evaluate tenancy, security, workflow depth, and long-term operational fit.",
        "schema_type": "WebPage",
        "segments": [
            {
                "title": "Tenant isolation",
                "body": "Each school can run on dedicated domain, controls, and policy boundaries.",
            },
            {
                "title": "Operational depth",
                "body": "Finance, academics, support, and compliance are first-class modules, not bolt-ons.",
            },
            {
                "title": "Command center visibility",
                "body": "Super-admin workflows centralize approvals, support queues, and health indicators.",
            },
        ],
    },
    "case-studies": {
        "label": "Case Studies",
        "seo_title": "RunMyCampus Case Studies - Real school implementation outcomes",
        "seo_description": "See how schools improve onboarding speed, intervention outcomes, and operational control with RunMyCampus.",
        "headline": "Results from real school operations.",
        "subheadline": "Case patterns show how teams reduce onboarding friction, improve intervention response, and scale governance.",
        "schema_type": "CollectionPage",
        "segments": [
            {
                "title": "Faster onboarding",
                "body": "New campuses provision with clearer timelines and less manual setup overhead.",
            },
            {
                "title": "Better intervention response",
                "body": "Risk monitoring and action-center workflows improve follow-through for at-risk learners.",
            },
            {
                "title": "Higher support visibility",
                "body": "Global queues and SLA tracking reduce blind spots across growing tenant portfolios.",
            },
        ],
    },
    "security-compliance": {
        "label": "Security & Compliance",
        "seo_title": "RunMyCampus Security & Compliance - FERPA/GDPR-ready controls",
        "seo_description": "Security-first tenancy with audit trails, access controls, compliance regions, and operational monitoring.",
        "headline": "Security and compliance built into daily operations.",
        "subheadline": "Protect tenant data with auditability, policy controls, and region-aware compliance defaults.",
        "schema_type": "WebPage",
        "segments": [
            {
                "title": "Tenant-scoped controls",
                "body": "Data access, policy settings, and activity traces stay scoped to each school.",
            },
            {
                "title": "Audit readiness",
                "body": "Operational events, support actions, and administrative changes remain reviewable.",
            },
            {
                "title": "Regional compliance posture",
                "body": "Map schools to compliance regions and align workflows to local obligations.",
            },
        ],
    },
    "integrations": {
        "label": "Integrations",
        "seo_title": "RunMyCampus Integrations - SIS, LMS, payments, and messaging",
        "seo_description": "Integrate LMS, payment gateways, messaging providers, and external services with governance controls.",
        "headline": "Integrations with governance, not chaos.",
        "subheadline": "Connect external systems while controlling activation, audit context, and operational blast radius.",
        "schema_type": "ItemList",
        "segments": [
            {
                "title": "Integration registry",
                "body": "Manage service entries and switch states in one governed control surface.",
            },
            {
                "title": "Interoperability APIs",
                "body": "Expose standards-aware endpoints for identity, academic workflows, and data exchange.",
            },
            {
                "title": "Operational safeguards",
                "body": "Track reasons, activity, and changes for every integration toggle.",
            },
        ],
    },
    "book-demo": {
        "label": "Book Demo",
        "seo_title": "Book a RunMyCampus Demo - See tenant operations live",
        "seo_description": "Schedule a platform demo focused on public experience, tenant access, and super-admin command workflows.",
        "headline": "Book a focused platform walkthrough.",
        "subheadline": "See public discovery, tenant login flow, and super-admin command center in one guided demo.",
        "schema_type": "Service",
        "segments": [
            {
                "title": "Public growth flow",
                "body": "Review SEO pages, discovery UX, and conversion paths from first visit to trial.",
            },
            {
                "title": "Tenant experience",
                "body": "Validate portal access journeys for school admins, teachers, and parents.",
            },
            {
                "title": "Super-admin control",
                "body": "Inspect mission-control workflows for approvals, billing visibility, and support governance.",
            },
        ],
    },
}

MARKETING_PAGE_EXTRAS = {
    "product": {
        "metrics": [
            {"value": "1", "label": "unified data model", "detail": "Admissions, academics, finance, and communication stay in one platform."},
            {"value": "4", "label": "core operator modules", "detail": "Enrollment, academics, operations, and support control surfaces."},
            {"value": "3", "label": "role portals", "detail": "Parent, teacher, and student experiences stay role-specific and auditable."},
            {"value": "24/7", "label": "operational continuity", "detail": "Manager-level workflows keep support and governance responsive."},
        ],
        "execution_blocks": [
            {
                "title": "Admissions to enrollment continuity",
                "body": "Lead capture, qualification, and onboarding transitions run without disconnected tooling.",
            },
            {
                "title": "Intervention action center",
                "body": "Risk signals route into assignment-ready intervention workflows for fast follow-through.",
            },
            {
                "title": "Governed integration model",
                "body": "Connect LMS, messaging, and payment providers with operational safeguards and traceability.",
            },
        ],
    },
    "solutions": {
        "metrics": [
            {"value": "3", "label": "deployment archetypes", "detail": "Single-campus, multi-campus, and regional operator models."},
            {"value": "195+", "label": "country-ready design", "detail": "Localization logic aligns terminology and compliance defaults by region."},
            {"value": "1", "label": "manager command center", "detail": "Central oversight with school-level autonomy across tenants."},
            {"value": "100%", "label": "subdomain isolation", "detail": "Tenant boundaries remain explicit and secure for every school."},
        ],
        "execution_blocks": [
            {
                "title": "Single-campus launch packs",
                "body": "Pre-configured patterns reduce setup time for school leads and operations teams.",
            },
            {
                "title": "Multi-campus governance rails",
                "body": "Standardize shared policy while preserving school identity, workflows, and ownership.",
            },
            {
                "title": "Regional adaptation without forks",
                "body": "Global registry hydration keeps language and compliance variants out of core business logic.",
            },
        ],
    },
    "pricing": {
        "metrics": [
            {"value": "3", "label": "clear plan bands", "detail": "Starter, Growth, and Enterprise White-label framing."},
            {"value": "0", "label": "migration guesswork", "detail": "Plan boundaries map to growth stages and governance requirements."},
            {"value": "1", "label": "billing oversight layer", "detail": "Manager workflows provide trial and usage visibility across tenants."},
            {"value": "Flexible", "label": "add-on model", "detail": "Activate advanced modules as schools scale operational complexity."},
        ],
        "execution_blocks": [
            {
                "title": "Transparent growth path",
                "body": "Schools can start lean, then add modules for analytics, integrations, and operator workflows.",
            },
            {
                "title": "Enterprise white-label readiness",
                "body": "High-scale operators get dedicated governance, compliance posture, and branding control.",
            },
            {
                "title": "Cost aligned to operations",
                "body": "Plans are designed around actual usage and institutional operating models, not feature sprawl.",
            },
        ],
    },
    "compare": {
        "metrics": [
            {"value": "1", "label": "canonical host contract", "detail": "Public, tenant, manager, API, and docs surfaces are explicitly separated."},
            {"value": "100%", "label": "subdomain tenancy", "detail": "No path-based tenant rendering in production contract."},
            {"value": "3", "label": "governance layers", "detail": "School-level control, manager oversight, and registry-based defaults."},
            {"value": "Audit-ready", "label": "operator traceability", "detail": "Support and provisioning actions remain attributable and reviewable."},
        ],
        "execution_blocks": [
            {
                "title": "Architecture fit assessment",
                "body": "Map your current operating model to strict host, tenancy, and governance requirements.",
            },
            {
                "title": "Migration risk reduction",
                "body": "Stage rollout with redirect compatibility and operational smoke checks before cutover.",
            },
            {
                "title": "Support readiness validation",
                "body": "Confirm manager workflow coverage for provisioning, escalation, and impersonation audit trails.",
            },
        ],
        "comparison_rows": [
            {
                "criterion": "Tenant isolation",
                "runmycampus": "Strict subdomain tenancy, isolated auth and data context.",
                "legacy": "Path-based tenancy increases cross-tenant risk and routing complexity.",
            },
            {
                "criterion": "Operations governance",
                "runmycampus": "Dedicated manager host for support, approvals, and health visibility.",
                "legacy": "Mixed admin routes on public host dilute control boundaries.",
            },
            {
                "criterion": "Localization strategy",
                "runmycampus": "Registry-driven hydration for terminology and compliance defaults.",
                "legacy": "Country-specific forks and hardcoded strings create maintenance debt.",
            },
            {
                "criterion": "Growth path",
                "runmycampus": "Plan-based scale from single campus to white-label enterprise.",
                "legacy": "Feature sprawl without operational stage alignment.",
            },
        ],
    },
    "case-studies": {
        "metrics": [
            {"value": "42%", "label": "faster onboarding cycles", "detail": "Template-led school launch patterns shorten go-live timelines."},
            {"value": "31%", "label": "faster intervention response", "detail": "Action-center workflows improve follow-through speed for at-risk learners."},
            {"value": "2.3x", "label": "support visibility gain", "detail": "Manager control workflows reduce unresolved queue blind spots."},
            {"value": "99.9%", "label": "platform continuity target", "detail": "Operational posture designed for day-to-day reliability."},
        ],
        "execution_blocks": [
            {
                "title": "Onboarding playbook rollout",
                "body": "Standardized launch templates reduce setup drift between schools and operators.",
            },
            {
                "title": "Intervention protocol adoption",
                "body": "Risk dashboards and assignment workflows improve consistency of learner support actions.",
            },
            {
                "title": "Support command workflow",
                "body": "Escalation pathways and audit traces improve decision velocity for manager teams.",
            },
        ],
        "case_cards": [
            {
                "title": "Multi-campus governance modernization",
                "result": "Reduced onboarding time while preserving campus identity autonomy.",
                "impact": "Faster go-live and clearer ownership boundaries.",
            },
            {
                "title": "Admissions-to-enrollment conversion lift",
                "result": "Unified enquiry, qualification, and onboarding workflow improved conversion flow.",
                "impact": "Lower handoff friction and better counselor throughput.",
            },
            {
                "title": "Regional localization program",
                "result": "Registry-driven terminology and compliance defaults removed regional hardcoding.",
                "impact": "Faster country rollout with lower maintenance overhead.",
            },
        ],
    },
    "book-demo": {
        "metrics": [
            {"value": "45 min", "label": "guided walkthrough", "detail": "Structured review of public, tenant, and manager experiences."},
            {"value": "3", "label": "live surface demonstrations", "detail": "Marketing conversion, tenant login, and manager operations in one session."},
            {"value": "1", "label": "architecture recommendation", "detail": "You receive a clear operating model fit summary."},
            {"value": "Next-day", "label": "follow-up package", "detail": "Implementation notes and rollout guidance after demo completion."},
        ],
        "execution_blocks": [
            {
                "title": "Discovery alignment",
                "body": "Capture your institution profile, constraints, and target operating outcomes before the walkthrough.",
            },
            {
                "title": "Live platform scenario",
                "body": "Run real workflows across public acquisition, tenant identity, and manager operations.",
            },
            {
                "title": "Actionable next-step plan",
                "body": "Receive a deployment sequence with conversion, governance, and onboarding priorities.",
            },
        ],
        "demo_agenda": [
            "Public authority flow: homepage, discovery, and conversion paths.",
            "Tenant experience: branded login, role portals, and workflow continuity.",
            "Manager control: provisioning, support desk, and audit traces.",
            "Implementation roadmap: phased rollout and success criteria.",
        ],
    },
}

TOPICAL_LANDING_DEFINITIONS = {
    "k12-school-management-system": {
        "label": "K12 School Management",
        "seo_title": "K12 School Management System | RunMyCampus",
        "seo_description": "K12-ready workflows for enrollment, attendance, grades, communication, and parent engagement.",
        "headline": "K12 operations in one platform.",
        "subheadline": "Coordinate academics, attendance, communication, and family engagement without tool sprawl.",
        "focus_points": [
            "Term and grading workflows aligned to school calendars.",
            "Parent and teacher portals with role-specific access.",
            "At-risk student insights for earlier intervention.",
        ],
    },
    "multi-campus-school-software": {
        "label": "Multi-Campus Operations",
        "seo_title": "Multi-Campus School Software | RunMyCampus",
        "seo_description": "Run multiple schools with centralized oversight and campus-level autonomy from a single platform.",
        "headline": "Multi-campus control without bottlenecks.",
        "subheadline": "Standardize governance while preserving each campus identity, workflows, and accountability.",
        "focus_points": [
            "Global super-admin command center for all tenants.",
            "Per-campus domain, branding, and policy isolation.",
            "Shared reporting for approvals, billing, and support.",
        ],
    },
    "student-passport-transcript-portability": {
        "label": "Student Passport Portability",
        "seo_title": "Student Passport & Transcript Portability | RunMyCampus",
        "seo_description": "Portable student passport and transcript workflows for smooth transitions across schools.",
        "headline": "Portable student records across school transitions.",
        "subheadline": "Enable secure transcript and passport continuity when learners move between institutions.",
        "focus_points": [
            "Global student passport identifiers for continuity.",
            "Transfer invite workflow between source and destination schools.",
            "Document-ready evidence trail for transcript portability.",
        ],
    },
}


def _safe_reverse(name: str, *, kwargs: dict | None = None) -> str:
    try:
        return reverse(name, kwargs=kwargs)
    except NoReverseMatch:
        return "#"
    except Exception:
        return "#"


def _marketing_nav() -> list[dict]:
    return [
        {"slug": slug, "label": page["label"], "path": f"/{slug}/"}
        for slug, page in MARKETING_PAGE_DEFINITIONS.items()
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

        ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "")
        )
        if not ip:
            return ""
        code = (get_country_from_ip(ip) or "").strip().upper()[:2]
        return code
    except Exception:
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


def _global_hreflang_entries(request, *, country_code: str, language_code: str) -> list[dict]:
    language = _normalize_language_code(language_code or "en")
    country = _normalize_country_code(country_code)
    if not country:
        return []
    entries = []
    supported = ["en", "fr", "pt", "ar"]
    for item in supported:
        path = f"/{item}/{country.lower()}/"
        entries.append({"hreflang": f"{item}-{country}", "href": _absolute_url(request, path)})
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
    brand = resolve_global_brand_context(country_code=country_code, language_code=language_code)
    seo = brand.get("seo_config") or {}
    default = {
        "headline": seo.get("headline") or "RunMyCampus",
        "subheadline": seo.get("subheadline") or "Global school operations, localized for every campus.",
        "features": seo.get("features") or [],
        "visual_variant": seo.get("visual_variant") or "",
        "seo_title": seo.get("seo_title") or "RunMyCampus - Global School Operations",
        "seo_description": seo.get("seo_description") or "Tenant-first school platform for academics, finance, and operations.",
    }

    country = _normalize_country_code(country_code)
    if not country:
        return default

    try:
        from apps.siteconfig.models import RegionalPitch

        pitch = RegionalPitch.objects.filter(country_code=country, is_active=True).first()
    except Exception:
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


def _tenant_example_slug_for_marketing() -> str | None:
    """
    Return a tenant slug suitable for marketing (e.g. regional landing).
    Prefer a non-legacy slug so links do not send users to school-not-found.
    """
    from django.conf import settings
    from apps.schools.models import School

    slug = getattr(settings, "TENANT_EXAMPLE_SLUG", None) or None
    if slug:
        return str(slug).strip().lower() or None
    school = (
        School.objects.filter(is_active=True)
        .exclude(slug__iexact="gilead-school")
        .exclude(subdomain__iexact="gilead-school")
        .order_by("created_at")
        .values_list("slug", flat=True)
        .first()
    )
    return school

def _marketing_context(request, *, country_code: str, language_code: str, regional: bool) -> dict:
    country = _normalize_country_code(country_code)
    brand = resolve_global_brand_context(country_code=country, language_code=language_code)
    language = _normalize_language_code(language_code, fallback=brand.get("primary_language") or "en")
    pitch = _get_regional_pitch(country, language)
    if regional and not country:
        raise Http404("Region not found")

    canonical_path = "/" if not regional else f"/{language}/{country.lower()}/"
    canonical_url = _absolute_url(request, canonical_path)
    hreflang_entries = _global_hreflang_entries(request, country_code=country, language_code=language)
    canonical_domain = get_canonical_base_domain()
    country_label = brand.get("country_name") or "Global"
    tenant_example_slug = _tenant_example_slug_for_marketing()
    tenant_login_path = "/authentication/login/"
    public_host = canonical_domain
    manager_host = f"manager.{canonical_domain}"
    api_host = f"api.{canonical_domain}"
    docs_host = f"docs.{canonical_domain}"
    tenant_host = f"{tenant_example_slug}.{canonical_domain}" if tenant_example_slug else f"your-school.{canonical_domain}"

    # School Identity card: link to tenant login only if we have a real example; else link to find school
    school_identity_primary_url = (
        _host_url(request, tenant_host, tenant_login_path)
        if tenant_example_slug
        else request.build_absolute_uri(_safe_reverse("find_school"))
    )
    school_identity_primary_label = "Tenant login" if tenant_example_slug else "Find your school"

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
        {"value": "3", "label": "dedicated surfaces", "detail": "Public, tenant, and manager host separation."},
        {"value": "195+", "label": "country-ready profiles", "detail": "Registry-driven localization and defaults."},
        {"value": "24/7", "label": "operator readiness", "detail": "Support and governance from manager workflows."},
        {"value": "100%", "label": "subdomain tenancy", "detail": "Strict isolation for tenant security boundaries."},
    ]

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
        "SHOW_HEADER_CONTEXT_STRIP": False,
    }


def _structured_data_for_page(*, page_type: str, canonical_url: str, name: str, description: str, path: str) -> dict:
    payload: dict = {
        "@context": "https://schema.org",
        "@type": page_type,
        "name": name,
        "url": canonical_url,
        "description": description,
        "isPartOf": {"@type": "WebSite", "name": "RunMyCampus", "url": canonical_url.rsplit(path, 1)[0] + "/"},
    }
    if page_type == "OfferCatalog":
        payload["itemListElement"] = [
            {"@type": "Offer", "name": "Starter"},
            {"@type": "Offer", "name": "Growth"},
            {"@type": "Offer", "name": "Enterprise"},
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
    geo_country = _get_country_from_request(request)
    ctx = _marketing_context(
        request,
        country_code=geo_country,
        language_code=(getattr(request, "LANGUAGE_CODE", "") or "en"),
        regional=False,
    )
    return render(request, "schools/marketing_landing.html", ctx)


@require_GET
def marketing_page(request, page_slug: str):
    page = MARKETING_PAGE_DEFINITIONS.get((page_slug or "").strip().lower())
    if not page:
        raise Http404("Page not found")

    base_ctx = _marketing_base_context(request)
    canonical_path = f"/{page_slug}/"
    canonical_url = _absolute_url(request, canonical_path)
    page_copy = deepcopy(page)
    page_copy["slug"] = page_slug
    page_copy["path"] = canonical_path
    page_extras = deepcopy(MARKETING_PAGE_EXTRAS.get(page_slug, {}))

    structured_data = _structured_data_for_page(
        page_type=page_copy.get("schema_type") or "WebPage",
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
        "page_extras": page_extras,
        "active_nav_slug": page_slug,
        "powerhouse_highlights": [
            "Predictive risk scoring and intervention action-center workflows.",
            "Student passport and transcript portability across schools.",
            "Super-admin mission control for approvals, billing, and support.",
        ],
    }
    return render(request, "schools/marketing_page.html", ctx)


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

    structured_data = _structured_data_for_page(
        page_type="CollectionPage",
        canonical_url=canonical_url,
        name=topic_copy.get("label") or "RunMyCampus",
        description=topic_copy.get("seo_description") or "",
        path=canonical_path,
    )

    ctx = {
        **base_ctx,
        "seo_title": topic_copy.get("seo_title"),
        "seo_description": topic_copy.get("seo_description"),
        "canonical_url": canonical_url,
        "structured_data_json": json.dumps(structured_data),
        "topic": topic_copy,
        "active_nav_slug": "solutions",
    }
    return render(request, "schools/marketing_topic_page.html", ctx)


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


@require_GET
def marketing_sitemap_xml(request):
    """
    Lightweight sitemap index for global marketing routes.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [_absolute_url(request, "/")]
    urls.extend([_absolute_url(request, item["path"]) for item in _marketing_nav()])
    urls.extend([_absolute_url(request, item["path"]) for item in _topical_nav()])
    urls.extend(
        [
            _absolute_url(request, "/discover/"),
            _absolute_url(request, "/find/"),
            _absolute_url(request, "/signup/"),
            _absolute_url(request, "/book-demo/"),
        ]
    )
    urls = list(dict.fromkeys(urls))
    try:
        from apps.siteconfig.models import GlobalBrandRegistry

        countries = list(
            GlobalBrandRegistry.objects.filter(is_active=True)
            .values_list("iso_code", "primary_language")
            .order_by("iso_code")
        )
    except Exception:
        countries = []

    if not countries:
        countries = [("CM", "fr"), ("CA", "en"), ("US", "en")]

    for iso_code, language in countries:
        code = (iso_code or "").strip().lower()
        lang = _normalize_language_code(language or "en")
        if not code:
            continue
        urls.append(_absolute_url(request, f"/{lang}/{code}/"))

    chunks = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>", "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"]
    for loc in urls:
        chunks.append("  <url>")
        chunks.append(f"    <loc>{loc}</loc>")
        chunks.append(f"    <lastmod>{now}</lastmod>")
        chunks.append("  </url>")
    chunks.append("</urlset>")
    return HttpResponse("\n".join(chunks), content_type="application/xml")
