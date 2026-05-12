# -*- coding: utf-8 -*-
"""
1066: Dynamic field definition / value read-only operator surface (Django admin remains CRUD).
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
def metadata_dynamic_fields_operator(request: HttpRequest) -> HttpResponse:
    context: dict = {}
    try:
        from apps.metadata.services import get_metadata_dynamic_field_operator_context

        context = get_metadata_dynamic_field_operator_context()
    except CONTROL_PLANE_METRIC_FAILURES as ex:
        logger.debug("metadata_dynamic_fields_operator: %s", ex)
        context = {
            "grouped_definitions": {},
            "operator_sections": [],
            "total_definitions": 0,
            "active_definitions": 0,
            "total_values": 0,
            "value_count_by_entity_type": {},
        }
    uc = getattr(request, "urlconf", None)
    try:
        context["entity_catalog_url"] = reverse(
            "siteconfig:entity_catalog_overview", urlconf=uc
        )
    except NoReverseMatch:
        context["entity_catalog_url"] = ""
    if is_control_plane_request(request):
        try:
            context["metadata_operator_hub_url"] = reverse(
                "siteconfig:metadata_operator_hub", urlconf=uc
            )
        except NoReverseMatch:
            context["metadata_operator_hub_url"] = ""
    else:
        context["metadata_operator_hub_url"] = ""
    try:
        context["admin_dynamic_definition_url"] = reverse(
            "admin:metadata_dynamicfielddefinition_changelist"
        )
    except NoReverseMatch:
        context["admin_dynamic_definition_url"] = ""
    try:
        context["admin_dynamic_value_url"] = reverse(
            "admin:metadata_dynamicfieldvalue_changelist"
        )
    except NoReverseMatch:
        context["admin_dynamic_value_url"] = ""
    return render(
        request,
        "siteconfig/metadata_dynamic_fields_operator.html",
        context,
    )
