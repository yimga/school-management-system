# -*- coding: utf-8 -*-
"""
Read-only config mutation audit evidence (Django admin changelist remains full CRUD).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.schools.super_views_constants import CONTROL_PLANE_METRIC_FAILURES

logger = logging.getLogger(__name__)


@staff_member_required(login_url=settings.LOGIN_URL)
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
    try:
        metadata_hub = reverse("siteconfig:metadata_operator_hub", urlconf=uc)
    except NoReverseMatch:
        metadata_hub = ""
    try:
        feature_audit = reverse("siteconfig:feature_control_audit", urlconf=uc)
    except NoReverseMatch:
        feature_audit = ""
    admin_changelist = ""
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
