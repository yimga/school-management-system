"""
Tenant-safe queryset narrowing for marketplace-linked developer apps.

Prefer ``apps.marketplace.sandbox.safe_queryset_for_app(queryset, request)`` when handling
an HTTP request (uses ``request.school``, installation binding, and API key / OAuth).

Use ``safe_queryset_for_app_install`` when you already resolved ``school`` and
``MarketplaceApp`` and need a filtered queryset without a request object.

HTTP handlers should continue to use ``apps.marketplace.sandbox.safe_queryset_for_app``
(imported here as ``safe_queryset_for_app_request`` for clarity).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

from apps.marketplace.sandbox import safe_queryset_for_app as safe_queryset_for_app_request

if TYPE_CHECKING:
    from apps.marketplace.models import MarketplaceApp
    from apps.schools.models import School

__all__ = ["safe_queryset_for_app_request", "safe_queryset_for_app_install"]


def safe_queryset_for_app_install(
    *,
    school: "School | None",
    marketplace_app: "MarketplaceApp | None",
    queryset: models.QuerySet,
    school_field: str = "school_id",
) -> models.QuerySet:
    """
    Restrict ``queryset`` to ``school`` when set; returns ``none()`` if school is missing.

    Pass ``marketplace_app`` when the model rows are tagged per-app (e.g. future
    ``app_id`` FK); currently only filters by tenant unless the queryset's model
    defines an ``app`` / ``marketplace_app`` field matching ``marketplace_app``.
    """
    if school is None:
        return queryset.none()
    qs = queryset.filter(**{school_field: school.id})
    if marketplace_app is None:
        return qs
    model = queryset.model
    for field_name in ("app_id", "marketplace_app_id", "app"):
        try:
            model._meta.get_field(field_name)
        except Exception:
            continue
        if field_name == "app":
            return qs.filter(app=marketplace_app)
        return qs.filter(**{field_name: marketplace_app.id})
    return qs
