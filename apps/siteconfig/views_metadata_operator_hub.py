# -*- coding: utf-8 -*-
"""
First-class metadata & lineage operator hub (read-only entry; CRUD remains Django admin when needed).
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.schools.control_plane import require_super_access_with_host


def _rev(request: HttpRequest, name: str, **kwargs) -> str:
    uc = getattr(request, "urlconf", None)
    try:
        if kwargs:
            return reverse(name, urlconf=uc, kwargs=kwargs)
        return reverse(name, urlconf=uc)
    except NoReverseMatch:
        return ""


@require_super_access_with_host
def metadata_operator_hub(request: HttpRequest) -> HttpResponse:
    """
    Curated control-plane entry for entity catalog, governance search, lineage graph,
    and platform metadata catalog. Django admin links are superuser-only fallbacks.
    """
    admin_entity = ""
    admin_config_audit = ""
    try:
        admin_entity = reverse("admin:metadata_entitycatalogentry_changelist")
    except NoReverseMatch:
        pass
    try:
        admin_config_audit = reverse("admin:metadata_configmutationauditlog_changelist")
    except NoReverseMatch:
        pass
    admin_dynamic_def = ""
    admin_dynamic_val = ""
    try:
        admin_dynamic_def = reverse("admin:metadata_dynamicfielddefinition_changelist")
    except NoReverseMatch:
        pass
    try:
        admin_dynamic_val = reverse("admin:metadata_dynamicfieldvalue_changelist")
    except NoReverseMatch:
        pass
    return render(
        request,
        "siteconfig/metadata_operator_hub.html",
        {
            "entity_catalog_url": _rev(request, "siteconfig:entity_catalog_overview"),
            "metadata_dynamic_fields_url": _rev(
                request, "siteconfig:metadata_dynamic_fields_operator"
            ),
            "governance_url": _rev(request, "metadata:metadata_governance"),
            "lineage_graph_url": _rev(request, "metadata:metadata_lineage_graph"),
            "full_metadata_catalog_url": _rev(request, "super:metadata_catalog"),
            "feature_control_url": _rev(request, "siteconfig:feature_control_panel"),
            "tenant_runtime_url": _rev(request, "siteconfig:tenant_runtime_configuration_hub"),
            "console_url": _rev(request, "siteconfig:console_domains_hub"),
            "config_mutation_evidence_url": _rev(
                request, "siteconfig:config_mutation_audit_evidence"
            ),
            "admin_entity_catalog_url": admin_entity,
            "admin_config_audit_url": admin_config_audit,
            "admin_dynamic_definition_url": admin_dynamic_def,
            "admin_dynamic_value_url": admin_dynamic_val,
        },
    )
