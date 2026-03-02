"""
RunMyCampus marketing and SEO endpoints.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.siteconfig.brand_registry import resolve_global_brand_context
from apps.siteconfig.global_catalog import GlobalGeoCatalog


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
    }


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
