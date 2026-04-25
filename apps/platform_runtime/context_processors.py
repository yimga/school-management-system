"""Template context processors for platform_runtime."""

from __future__ import annotations

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from apps.platform_runtime.shell_contract import resolve_shell_contract


def rum_ingest_context(request):
    """
    Expose RUM endpoint + token to templates when RUM_INGEST_KEY is configured (>= 16 chars).
    """
    key = (getattr(settings, "RUM_INGEST_KEY", None) or "").strip()
    if len(key) < 16:
        return {"rum_ingest_url": None, "rum_ingest_key": None}
    try:
        path = reverse("rum_ingest")
    except NoReverseMatch:
        return {"rum_ingest_url": None, "rum_ingest_key": None}
    url = request.build_absolute_uri(path)
    return {"rum_ingest_url": url, "rum_ingest_key": key}


def shell_contract_context(request):
    """
    Expose ``rmc_shell`` (route/layout/nav classification) to all template renders.

    See ``apps.platform_runtime.shell_contract`` — descriptive only, not authorization.
    """
    return {"rmc_shell": resolve_shell_contract(request)}
