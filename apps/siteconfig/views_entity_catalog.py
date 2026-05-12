# -*- coding: utf-8 -*-
"""
Control-plane entity catalog overview (read-only; CRUD remains Django admin or imports).
"""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.schools.control_plane import (
    is_control_plane_request,
    require_super_access_with_host,
)
from apps.schools.super_views_constants import CONTROL_PLANE_METRIC_FAILURES

logger = logging.getLogger(__name__)


@require_super_access_with_host
def entity_catalog_overview(request: HttpRequest) -> HttpResponse:
    """
    First-class operator view: searchable entity/field catalog slice (same query as
    ``super:metadata_catalog`` without the platform checklist block).
    """
    entities: list = []
    query_display = ""
    try:
        from apps.metadata.services import get_metadata_catalog_entity_rows

        entities, query_display = get_metadata_catalog_entity_rows(
            request.GET, max_entities=200
        )
    except CONTROL_PLANE_METRIC_FAILURES as ex:
        logger.debug("entity_catalog_overview: catalog rows unavailable: %s", ex)
    try:
        admin_changelist = reverse("admin:metadata_entitycatalogentry_changelist")
    except NoReverseMatch:
        admin_changelist = ""
    try:
        admin_config_audit = reverse("admin:metadata_configmutationauditlog_changelist")
    except NoReverseMatch:
        admin_config_audit = ""
    uc = getattr(request, "urlconf", None)
    try:
        full_catalog = reverse("super:metadata_catalog", urlconf=uc)
    except NoReverseMatch:
        full_catalog = ""
    if is_control_plane_request(request):
        try:
            metadata_operator_hub_url = reverse(
                "siteconfig:metadata_operator_hub", urlconf=uc
            )
        except NoReverseMatch:
            metadata_operator_hub_url = ""
    else:
        metadata_operator_hub_url = ""
    try:
        metadata_dynamic_fields_url = reverse(
            "siteconfig:metadata_dynamic_fields_operator", urlconf=uc
        )
    except NoReverseMatch:
        metadata_dynamic_fields_url = ""
    return render(
        request,
        "siteconfig/entity_catalog_overview.html",
        {
            "entities": entities,
            "query": query_display,
            "lifecycle_all": request.GET.get("lifecycle") == "all",
            "full_catalog_url": full_catalog,
            "metadata_operator_hub_url": metadata_operator_hub_url,
            "metadata_dynamic_fields_url": metadata_dynamic_fields_url,
            "admin_entity_catalog_url": admin_changelist,
            "admin_config_audit_url": admin_config_audit,
        },
    )
