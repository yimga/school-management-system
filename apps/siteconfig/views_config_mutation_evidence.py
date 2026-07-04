# -*- coding: utf-8 -*-
"""
Read-only config mutation audit evidence (Django admin changelist remains full CRUD).
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


def _is_manager_scope(request: HttpRequest) -> bool:
    kind = getattr(request, "public_host_kind", None)
    urlconf = getattr(request, "urlconf", None)
    return (
        (kind == "manager" or urlconf == "config.manager_urls")
        and getattr(request, "school", None) is None
    )


@require_super_access_with_host
def config_mutation_audit_evidence(request: HttpRequest) -> HttpResponse:
    rows: list = []
    try:
        from apps.metadata.models import ConfigMutationAuditLog

        rows = list(
            ConfigMutationAuditLog.objects.order_by("-created_at")[:200]
        )
    except CONTROL_PLANE_METRIC_FAILURES as ex:
        logger.debug("config_mutation_audit_evidence: %s", ex)
    uc = getattr(request, "urlconf", None)
    if is_control_plane_request(request):
        try:
            metadata_hub = reverse("siteconfig:metadata_operator_hub", urlconf=uc)
        except NoReverseMatch:
            metadata_hub = ""
    else:
        metadata_hub = ""
    try:
        feature_audit = reverse("siteconfig:feature_control_audit", urlconf=uc)
    except NoReverseMatch:
        feature_audit = ""
    admin_changelist = ""
    if _is_manager_scope(request):
        try:
            admin_changelist = reverse("admin:metadata_configmutationauditlog_changelist")
        except NoReverseMatch:
            pass
    return render(
        request,
        "siteconfig/config_mutation_audit_evidence.html",
        {
            "rows": rows,
            "metadata_operator_hub_url": metadata_hub,
            "feature_control_audit_url": feature_audit,
            "admin_config_mutation_changelist_url": admin_changelist,
        },
    )
