"""
Central metadata catalog API (Phase 8).
Exposes schema, experience, runtime, registry, integration, and governance metadata.
All tenant-facing behavior should resolve via runtime; this catalog is for operators and tooling.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from django.db.models import Count

from apps.policies_rules.models import PolicyBundle
from apps.runtime_blueprints.models import Blueprint, DashboardPack, DashboardWidget, WorkflowPack
from apps.siteconfig.workflow_registry import get_workflow_catalog

# Canonical entity list aligned with docs/architecture/canonical_education_graph.md
_SCHEMA_ENTITIES = [
    {"name": "Person", "owner": "Identity & Access", "source_of_truth": "User"},
    {"name": "Student", "owner": "People", "source_of_truth": "StudentProfile"},
    {"name": "Guardian", "owner": "People", "source_of_truth": "StudentGuardian"},
    {"name": "Enrollment", "owner": "Academics", "source_of_truth": "Enrollment"},
    {"name": "Course", "owner": "Academics", "source_of_truth": "Course"},
    {"name": "Invoice", "owner": "Finance", "source_of_truth": "Invoice"},
    {"name": "Payment", "owner": "Finance", "source_of_truth": "Payment"},
]


def get_schema_metadata(school_id: Optional[Any] = None) -> Dict[str, Any]:
    """
    Schema metadata: entities, fields, relationships, validation, state machines.
    Canonical entities from docs/architecture/canonical_education_graph.md.
    """
    return {
        "schema_version": "1.0",
        "entities": list(_SCHEMA_ENTITIES),
        "scope": "platform",
        "documentation": "docs/architecture/canonical_education_graph.md",
    }


def get_experience_metadata(school_id: Optional[Any] = None) -> Dict[str, Any]:
    """
    Experience metadata: layouts, forms, navigation, dashboards, widgets, portal, themes.
    """
    try:
        from apps.siteconfig.models import ThemePack
        theme_packs = list(
            ThemePack.objects.filter(is_active=True).values("id", "name", "slug").order_by("name")[:100]
        )
    except Exception:
        theme_packs = []
    try:
        widgets = list(
            DashboardWidget.objects.values("code", "name", "chart_type")
            .annotate(count=Count("id"))
            .order_by("code")[:100]
        )
    except Exception:
        widgets = []
    return {
        "schema_version": "1.0",
        "theme_packs": theme_packs,
        "dashboard_widgets": widgets,
        "scope": "platform",
        "documentation": "docs/architecture/central_metadata_catalog.md",
    }


def get_runtime_metadata(school_id: Optional[Any] = None) -> Dict[str, Any]:
    """
    Runtime metadata: blueprints, workflow/dashboard packs, policy bundles, entitlements.
    """
    try:
        blueprints = list(
            Blueprint.objects.filter(is_active=True).values("id", "code", "family", "name").order_by("code")[:200]
        )
    except Exception:
        blueprints = []
    try:
        workflow_packs = list(
            WorkflowPack.objects.filter(is_active=True).values("id", "code", "family", "name", "version").order_by("code")[:200]
        )
    except Exception:
        workflow_packs = []
    try:
        dashboard_packs = list(
            DashboardPack.objects.filter(is_active=True).values("id", "code", "family", "name", "version").order_by("code")[:200]
        )
    except Exception:
        dashboard_packs = []
    try:
        policy_bundles = list(
            PolicyBundle.objects.filter(is_active=True).values("id", "code", "name", "version", "country_scope").order_by("code", "name")[:200]
        )
    except Exception:
        policy_bundles = []
    try:
        workflow_catalog = get_workflow_catalog()
    except Exception:
        workflow_catalog = {}
    return {
        "schema_version": "1.0",
        "blueprints": blueprints,
        "workflow_packs": workflow_packs,
        "dashboard_packs": dashboard_packs,
        "policy_bundles": policy_bundles,
        "workflow_catalog": workflow_catalog,
        "scope": "platform",
        "documentation": "docs/architecture/orchestration_layer.md",
    }


def get_registry_metadata(school_id: Optional[Any] = None) -> Dict[str, Any]:
    """
    Registry metadata: country, locale, calendar, terminology, grading scale, education system.
    """
    try:
        from apps.registries.models import CountryRegistry
        countries = list(
            CountryRegistry.objects.filter(is_active=True).values("code", "name").order_by("name")[:300]
        )
    except Exception:
        countries = []
    return {
        "schema_version": "1.0",
        "countries": countries,
        "scope": "platform",
        "documentation": "docs/architecture/central_metadata_catalog.md",
    }


def get_integration_metadata(school_id: Optional[Any] = None) -> Dict[str, Any]:
    """
    Integration metadata: providers, connectors, scopes, webhooks, sync mappings.
    """
    try:
        from apps.siteconfig.models import Integration
        integrations = list(
            Integration.objects.values("provider", "slug", "enabled").distinct()[:100]
        )
    except Exception:
        integrations = []
    return {
        "schema_version": "1.0",
        "integrations": integrations,
        "scope": "platform",
        "documentation": "docs/architecture/central_metadata_catalog.md",
    }


def get_governance_metadata(school_id: Optional[Any] = None) -> Dict[str, Any]:
    """
    Governance metadata: ownership, scope, version, lifecycle, approval, compatibility, rollback.
    """
    return {
        "schema_version": "1.0",
        "rules": [
            "Metadata must be versioned and auditable",
            "High-impact metadata supports rollback",
            "Scope: platform | regional | blueprint | pack | tenant",
        ],
        "scope": "platform",
        "documentation": "docs/architecture/orchestration_layer.md",
    }


def get_catalog(school_id: Optional[Any] = None) -> Dict[str, Any]:
    """Return full catalog (all categories)."""
    return {
        "schema": get_schema_metadata(school_id),
        "experience": get_experience_metadata(school_id),
        "runtime": get_runtime_metadata(school_id),
        "registry": get_registry_metadata(school_id),
        "integration": get_integration_metadata(school_id),
        "governance": get_governance_metadata(school_id),
    }
