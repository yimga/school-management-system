"""Resolve marketing footer links on the manager host via the public URLconf."""

from __future__ import annotations

from django import template
from django.conf import settings
from django.urls import NoReverseMatch, reverse

register = template.Library()

_PUBLIC_URLCONF = "config.public_urls"

_PUBLIC_URL_FALLBACKS: dict[str, tuple[str, str]] = {
    "marketing_careers": ("marketing_company", ""),
    "marketing_brand_assets": ("marketing_company", ""),
    "marketing_hardware_store": ("marketing_app_marketplace", ""),
    "marketing_solutions_higher_ed": ("marketing_solutions", ""),
    "marketing_solutions_k12_districts": ("marketing_solutions_k12_schools", ""),
    "marketing_training_academies": ("marketing_resources_guides", ""),
    "marketing_teacher_communities": ("marketing_resources_guides", ""),
    "marketing_lesson_planning": ("marketing_resources_guides", ""),
    "marketing_infrastructure_map": ("marketing_trust_center", "#infrastructure-map"),
    "marketing_security_matrix": ("marketing_security_compliance", "#security-matrix"),
    "marketing_legal_ferpa": ("marketing_trust_ferpa", ""),
    "marketing_legal_coppa": ("marketing_trust_coppa", ""),
    "marketing_legal_gdpr": ("marketing_trust_gdpr", ""),
    "marketing_legal_wcag": ("marketing_trust_accessibility", ""),
    "marketing_legal_terms": ("marketing_trust_center", "#terms"),
    "marketing_legal_cookie": ("marketing_trust_center", "#cookies"),
}


def _reverse_public(url_name: str, suffix: str, *, host_kind: str | None, base: str) -> str | None:
    try:
        return reverse(url_name) + suffix
    except NoReverseMatch:
        pass
    try:
        path = reverse(url_name, urlconf=_PUBLIC_URLCONF)
        if host_kind in ("manager", "tenant") and base:
            return f"{base}{path}{suffix}"
        return path + suffix
    except NoReverseMatch:
        return None


@register.simple_tag(takes_context=True)
def marketing_public_href(context, url_name: str, *suffix_parts: str) -> str:
    """
    On manager.runmycampus.com, marketing routes live on runmycampus.com.
    On the public marketing host, use the local named URL.
    """
    suffix = "".join(suffix_parts)
    request = context.get("request")
    host_kind = getattr(request, "public_host_kind", None) if request else None

    base = (getattr(settings, "PUBLIC_SITE_URL", "") or "").rstrip("/")
    resolved = _reverse_public(url_name, suffix, host_kind=host_kind, base=base)
    if resolved:
        return resolved
    fallback = _PUBLIC_URL_FALLBACKS.get(url_name)
    if fallback:
        fallback_name, fallback_suffix = fallback
        resolved = _reverse_public(fallback_name, fallback_suffix + suffix, host_kind=host_kind, base=base)
        if resolved:
            return resolved
    if base and host_kind in ("manager", "tenant"):
        return f"{base}/{suffix.lstrip('/')}"
    return "/"
