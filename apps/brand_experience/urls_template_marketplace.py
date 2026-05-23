"""Tenant ExperienceTemplate marketplace URL patterns.

Mounted under ``/school/studio/templates/`` by the root tenant URL graph.
"""

from __future__ import annotations

from django.urls import path

from apps.brand_experience.views_template_marketplace import (
    tenant_local_first_catalog,
    tenant_template_ai_recommendation,
    tenant_template_apply,
    tenant_template_compare,
    tenant_template_customize,
    tenant_template_detail,
    tenant_template_marketplace,
    tenant_template_preview,
    tenant_template_rollback,
)

app_name = "template_marketplace"

urlpatterns = [
    path("", tenant_template_marketplace, name="browse"),
    path("recommend/", tenant_template_ai_recommendation, name="ai_recommend"),
    path("local/<str:country_code>/", tenant_local_first_catalog, name="local_catalog"),
    path("<slug:key>/", tenant_template_detail, name="detail"),
    path("<slug:key>/preview/", tenant_template_preview, name="preview"),
    path("<slug:key>/compare/", tenant_template_compare, name="compare"),
    path("<slug:key>/apply/", tenant_template_apply, name="apply"),
    path("<slug:key>/rollback/", tenant_template_rollback, name="rollback"),
    path("<slug:key>/customize/", tenant_template_customize, name="customize"),
]
