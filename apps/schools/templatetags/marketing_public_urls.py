"""Resolve marketing footer links on the manager host via the public URLconf."""

from __future__ import annotations

from django import template
from django.conf import settings
from django.urls import NoReverseMatch, reverse

register = template.Library()

_PUBLIC_URLCONF = "config.public_urls"


@register.simple_tag(takes_context=True)
def marketing_public_href(context, url_name: str, *suffix_parts: str) -> str:
    """
    On manager.runmycampus.com, marketing routes live on runmycampus.com.
    On the public marketing host, use the local named URL.
    """
    suffix = "".join(suffix_parts)
    request = context.get("request")
    host_kind = getattr(request, "public_host_kind", None) if request else None

    try:
        if host_kind == "manager":
            try:
                return reverse(url_name) + suffix
            except NoReverseMatch:
                path = reverse(url_name, urlconf=_PUBLIC_URLCONF)
                base = (getattr(settings, "PUBLIC_SITE_URL", "") or "").rstrip("/")
                return f"{base}{path}{suffix}"
        return reverse(url_name) + suffix
    except NoReverseMatch:
        base = (getattr(settings, "PUBLIC_SITE_URL", "") or "").rstrip("/")
        return f"{base}/{suffix.lstrip('/')}" if host_kind == "manager" else "#"
