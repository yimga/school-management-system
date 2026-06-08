"""
Route-level page explainers for operator + tenant shells.

Resolves copy from workflow registry routes, explicit overrides, and namespace defaults.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

# url_name (with optional namespace) → page help
ROUTE_HELP_OVERRIDES: dict[str, dict[str, Any]] = {
    "schoolops:email_configure": {
        "title": _("Email configuration"),
        "body": _(
            "Set platform SMTP relay and defaults for tenant notification delivery. "
            "Secrets are encrypted at rest."
        ),
        "surface": "operator",
        "fields": ("smtp_host", "smtp_port", "smtp_username", "smtp_password", "from_email"),
    },
    "finance:marketplace_integration_credentials": {
        "title": _("Integration credentials"),
        "body": _(
            "Store adapter secrets for marketplace apps. Rotate after vendor or staff changes."
        ),
        "surface": "tenant",
        "fields": ("api_key", "client_secret", "webhook_secret", "token"),
    },
    "accounts:district_interop_hub": {
        "title": _("District interoperability"),
        "body": _(
            "Connect LMS and roster systems across schools in your district. "
            "Each connector scopes to authorized tenants."
        ),
        "surface": "operator",
        "fields": ("lms_url", "client_id", "client_secret", "api_token"),
    },
    "finance:invoices": {
        "title": _("Invoices"),
        "body": _("Search, filter, and export fee invoices. Status drives reminders and parent visibility."),
        "surface": "tenant",
        "fields": ("reference", "status", "due_date"),
    },
    "people:backend_applicant_list": {
        "title": _("Applicants"),
        "body": _("Admissions pipeline from enquiry through enrollment."),
        "surface": "tenant",
        "fields": ("stage", "status"),
    },
    "super:signup_verifications": {
        "title": _("Signup verifications"),
        "body": _("Review new school signups and retry provisioning when setup stalls."),
        "surface": "operator",
        "fields": (),
    },
}

# Django app namespace → catalog entity prefix for field manifests
NAMESPACE_ENTITY_PREFIX: dict[str, str] = {
    "accounts": "accounts",
    "academics": "academics",
    "admissions": "admissions",
    "analytics": "analytics",
    "apicenter": "apicenter",
    "assist_dock": "assist_dock",
    "automation": "automation",
    "billing": "billing",
    "brand_experience": "brand_experience",
    "communication": "communication",
    "compliance": "compliance",
    "customersuccess": "customersuccess",
    "emis": "emis",
    "evals": "evals",
    "events": "events",
    "feedback": "feedback",
    "finance": "finance",
    "global_registries": "global_registries",
    "governance": "governance",
    "integrations_marketplace": "integrations_marketplace",
    "lifecycle": "lifecycle",
    "marketplace": "marketplace",
    "metadata": "metadata",
    "migration_cloud": "migration_cloud",
    "observability": "observability",
    "orchestration": "orchestration",
    "packages": "packages",
    "payroll": "payroll",
    "people": "people",
    "plans_entitlements": "plans_entitlements",
    "platform_runtime": "platform_runtime",
    "policies": "policies",
    "portal": "portal",
    "registries": "registries",
    "reports": "reports",
    "requests": "requests",
    "runtime_blueprints": "runtime_blueprints",
    "safeguarding": "safeguarding",
    "sales": "sales",
    "school_events": "school_events",
    "schoolops": "operator",
    "schools": "schools",
    "setup_studio": "setup_studio",
    "siteconfig": "siteconfig",
    "social_media": "social_media",
    "student360": "student360",
    "studio_os": "studio_os",
    "sync_engine": "sync_engine",
    "tenancy": "tenancy",
    "super": "super",
    "authentication": "portal",
}

# Fallback when no workflow or override matches
_NAMESPACE_DEFAULTS: dict[str, dict[str, str]] = {
    "operator": {
        "title": _("Operator workspace"),
        "body": _("Platform-wide tools for provisioning, billing, and migration."),
    },
    "tenant": {
        "title": _("School workspace"),
        "body": _("Day-to-day workflows for staff, teachers, and administrators."),
    },
}


def _workflow_route_help() -> dict[str, dict[str, Any]]:
    from apps.platform_runtime.workflow_registry import (
        AUDIENCE_FOUNDER,
        AUDIENCE_OPERATOR,
        AUDIENCE_PARENT,
        AUDIENCE_STUDENT,
        AUDIENCE_TEACHER,
        AUDIENCE_TENANT_ADMIN,
        WORKFLOWS,
    )

    operator_audiences = {AUDIENCE_OPERATOR, AUDIENCE_FOUNDER}
    tenant_audiences = {
        AUDIENCE_TENANT_ADMIN,
        AUDIENCE_TEACHER,
        AUDIENCE_PARENT,
        AUDIENCE_STUDENT,
    }
    out: dict[str, dict[str, Any]] = {}
    for workflow in WORKFLOWS.values():
        route = getattr(workflow, "route", None)
        if not route or not isinstance(route, str) or route.startswith("/"):
            continue
        if route in out:
            continue
        if workflow.audience in operator_audiences:
            surface = "operator"
        elif workflow.audience in tenant_audiences:
            surface = "tenant"
        else:
            surface = "public"
        out[route] = {
            "title": workflow.title,
            "body": workflow.purpose,
            "surface": surface,
            "workflow_key": workflow.key,
            "fields": (),
        }
    return out


_WORKFLOW_ROUTE_HELP: dict[str, dict[str, Any]] | None = None


def _merged_route_index() -> dict[str, dict[str, Any]]:
    global _WORKFLOW_ROUTE_HELP
    if _WORKFLOW_ROUTE_HELP is None:
        _WORKFLOW_ROUTE_HELP = _workflow_route_help()
    merged = dict(_WORKFLOW_ROUTE_HELP)
    merged.update(ROUTE_HELP_OVERRIDES)
    return merged


def _view_name(request: Any) -> str:
    match = getattr(request, "resolver_match", None)
    if match is None:
        return ""
    namespace = getattr(match, "namespace", None) or ""
    url_name = getattr(match, "url_name", None) or ""
    if namespace and url_name:
        return f"{namespace}:{url_name}"
    return url_name or getattr(match, "view_name", None) or ""


def _host_surface(request: Any) -> str:
    kind = getattr(request, "public_host_kind", None)
    if kind == "manager":
        return "operator"
    return "tenant"


def resolve_route_help(request: Any) -> dict[str, Any]:
    """Return {title, body, surface, workflow_key?, fields} for the current route."""
    view_name = _view_name(request)
    if not view_name:
        surface = _host_surface(request)
        default = _NAMESPACE_DEFAULTS.get(surface, _NAMESPACE_DEFAULTS["tenant"])
        return {"title": default["title"], "body": default["body"], "surface": surface, "fields": ()}

    entry = _merged_route_index().get(view_name)
    if entry:
        return {
            "title": entry.get("title", ""),
            "body": entry.get("body", ""),
            "surface": entry.get("surface") or _host_surface(request),
            "workflow_key": entry.get("workflow_key", ""),
            "fields": tuple(entry.get("fields") or ()),
        }

    match = getattr(request, "resolver_match", None)
    namespace = getattr(match, "namespace", None) if match else None
    surface = _host_surface(request)
    default = _NAMESPACE_DEFAULTS.get(surface, _NAMESPACE_DEFAULTS["tenant"])
    return {
        "title": default["title"],
        "body": default["body"],
        "surface": surface,
        "namespace": namespace or "",
        "fields": (),
    }


def entity_prefix_for_request(request: Any) -> str:
    """Catalog entity prefix used to build auto field manifests."""
    match = getattr(request, "resolver_match", None)
    namespace = getattr(match, "namespace", None) if match else None
    if namespace and namespace in NAMESPACE_ENTITY_PREFIX:
        return NAMESPACE_ENTITY_PREFIX[namespace]
    return "common" if _host_surface(request) == "tenant" else "operator"
