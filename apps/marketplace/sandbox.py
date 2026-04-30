"""Tenant-safe queryset helpers for app-authenticated API requests."""

from __future__ import annotations

from django.db import models
from django.http import HttpRequest


def safe_queryset_for_app(
    queryset: models.QuerySet,
    request: HttpRequest,
    *,
    school_field: str = "school_id",
) -> models.QuerySet:
    """
    Restrict any queryset to the current tenant when ``request.school`` is set.
    If an API key is bound to a marketplace installation, ensure the installation
    belongs to the same school (blocks cross-tenant escalations).
    """
    school = getattr(request, "school", None)
    if school is None:
        return queryset.none()

    key = getattr(request, "app_api_key", None)
    inst = getattr(request, "app_installation", None)
    if key is not None and inst is not None:
        if str(inst.school_id) != str(school.id):
            return queryset.none()

    return queryset.filter(**{school_field: school.id})
