"""
Control plane sidebar navigation registry.
Builds grouped nav items for /super/ from a single source of truth.
Used by context processor to inject CONTROL_PLANE_NAV; template renders from it.
Each item has "id" for favorites/pins (Phase 8).
"""
from django.urls import reverse


def _safe_reverse(url_name, urlconf=None, kwargs=None, args=None):
    try:
        if args:
            return reverse(url_name, args=args, urlconf=urlconf)
        return reverse(url_name, kwargs=kwargs or {}, urlconf=urlconf)
    except Exception:
        return None


def build_control_plane_nav(request):
    """
    Return list of groups, each with "label" (optional section heading) and "items"
    (list of dicts: id, label, url, icon). Only includes items whose url resolved.
    """
    urlconf = getattr(request, "urlconf", None) or "config.manager_urls"
    groups = []

    def add_group(label, items):
        resolved = []
        for item in items:
            url = _safe_reverse(
                item["url_name"],
                urlconf=urlconf,
                kwargs=item.get("kwargs"),
                args=item.get("args"),
            )
            if url:
                resolved.append({
                    "id": item.get("id", ""),
                    "label": item["label"],
                    "url": url,
                    "icon": item.get("icon", "bi-circle"),
                })
        if resolved:
            groups.append({"label": label, "items": resolved})

    add_group(None, [
        {"id": "super_dashboard", "label": "Dashboard", "url_name": "super:dashboard", "icon": "bi-speedometer2"},
        {"id": "super_command_center", "label": "Command Center", "url_name": "super:command_center", "icon": "bi-list-check"},
        {"id": "super_provision", "label": "Provision tenant", "url_name": "super:create_school_wizard", "icon": "bi-plus-circle"},
        {"id": "super_billing", "label": "Billing", "url_name": "super:billing_dashboard", "icon": "bi-credit-card"},
        {"id": "super_support", "label": "Support", "url_name": "super:support_dashboard", "icon": "bi-headset"},
    ])
    add_group("Marketplace", [
        {"id": "super_governance", "label": "Governance", "url_name": "super:marketplace_governance", "icon": "bi-shield-check"},
        {"id": "super_blueprint_marketplace", "label": "Blueprints", "url_name": "super:blueprint_marketplace", "icon": "bi-collection"},
        {"id": "super_app_catalog", "label": "App catalog", "url_name": "super:app_catalog", "icon": "bi-grid-3x3-gap"},
        {"id": "super_customer_success", "label": "Customer Success", "url_name": "super:customer_success_dashboard", "icon": "bi-graph-up-arrow"},
    ])
    add_group(None, [
        {"id": "super_migration", "label": "Migration", "url_name": "super:migration_cloud", "icon": "bi-cloud-arrow-up"},
        {"id": "super_usage", "label": "Usage", "url_name": "super:usage", "icon": "bi-bar-chart"},
        {"id": "super_pulse", "label": "Pulse", "url_name": "super:pulse", "icon": "bi-activity"},
        {"id": "super_tenant_health", "label": "Tenant Health", "url_name": "super:tenant_health", "icon": "bi-heart-pulse"},
        {"id": "super_compliance", "label": "Compliance", "url_name": "super:compliance_overview", "icon": "bi-shield-check"},
        {"id": "super_analytics", "label": "Analytics", "url_name": "super:analytics_overview", "icon": "bi-graph-up"},
        {"id": "super_incidents", "label": "Incidents", "url_name": "platform_incidents_console", "icon": "bi-exclamation-triangle"},
        {"id": "super_runtime_inspector", "label": "Runtime inspector", "url_name": "super:runtime_inspector", "icon": "bi-code-square"},
        {"id": "super_workflow_simulator", "label": "Workflow simulator", "url_name": "super:workflow_simulator", "icon": "bi-diagram-3"},
    ])
    add_group("Packs & registries", [
        {"id": "super_registries", "label": "Registries", "url_name": "super:registries_overview", "icon": "bi-globe"},
        {"id": "super_blueprints", "label": "Blueprints", "url_name": "super:blueprints_catalog", "icon": "bi-diagram-3"},
        {"id": "super_policies", "label": "Policies", "url_name": "super:policies_catalog", "icon": "bi-shield"},
        {"id": "super_workflow_packs", "label": "Workflow Packs", "url_name": "super:workflow_packs_catalog", "icon": "bi-diagram-2"},
        {"id": "super_dashboard_packs", "label": "Dashboard Packs", "url_name": "super:dashboard_packs_catalog", "icon": "bi-grid"},
    ])
    add_group(None, [
        {"id": "admin_index", "label": "Configuration Engine", "url_name": "admin:index", "icon": "bi-gear-wide-connected"},
    ])

    return groups
