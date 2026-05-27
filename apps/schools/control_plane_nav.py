"""
Control plane sidebar navigation registry.
Builds grouped nav items for /super/ from a single source of truth.
Used by context processor to inject CONTROL_PLANE_NAV; template renders from it.
Each item has "id" for favorites/pins (Phase 8).

§8.0.4 Sidebar cleanup: One role-aware sidebar + command palette (Ctrl+K);
no duplicates, legacy labels, or internal jargon. "Config center" (Configuration Control Center)
is the single entry for bounded config; "Open in backoffice" only for rare/legacy (LEGACY_PATH_INVENTORY).
"""

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _


def _safe_reverse(url_name, urlconf=None, kwargs=None, args=None):
    try:
        if args:
            return reverse(url_name, args=args, urlconf=urlconf)
        return reverse(url_name, kwargs=kwargs or {}, urlconf=urlconf)
    except NoReverseMatch:
        return None


def _platform_admin_bridge_nav_items():
    """
    Sidebar entries for ``super:admin_bridge`` (registry keys with ``show_in_nav``).
    Keeps ids/labels/icons aligned with ``super_admin_bridge_registry``.
    """
    from apps.schools.super_admin_bridge_registry import (
        PLATFORM_ADMIN_BRIDGE_ORDER,
        PLATFORM_ADMIN_BRIDGES,
    )

    items = []
    for key in PLATFORM_ADMIN_BRIDGE_ORDER:
        meta = PLATFORM_ADMIN_BRIDGES.get(key)
        if not meta or not meta.get("show_in_nav"):
            continue
        items.append(
            {
                "id": meta["nav_id"],
                "label": str(meta["nav_label"]),
                "url_name": "super:admin_bridge",
                "kwargs": {"bridge_key": key},
                "icon": meta.get("nav_icon", "bi-box-arrow-up-right"),
            }
        )
    return items


def _platform_admin_bridge_nav_items_direct(urlconf=None):
    """
    Advanced /super/ sidebar: link straight to platform-admin changelists.

    Avoids an extra 302 via ``super:admin_bridge`` (bookmarks and hub tiles still use bridges).
    """
    from apps.schools.super_admin_bridge_registry import (
        PLATFORM_ADMIN_BRIDGE_ORDER,
        PLATFORM_ADMIN_BRIDGES,
    )

    items = []
    for key in PLATFORM_ADMIN_BRIDGE_ORDER:
        meta = PLATFORM_ADMIN_BRIDGES.get(key)
        if not meta or not meta.get("show_in_nav"):
            continue
        admin_url_name = meta.get("admin_url")
        if not admin_url_name:
            continue
        url = _safe_reverse(str(admin_url_name), urlconf=urlconf)
        if not url:
            continue
        items.append(
            {
                "id": meta["nav_id"],
                "label": str(meta["nav_label"]),
                "url": url,
                "icon": meta.get("nav_icon", "bi-box-arrow-up-right"),
            }
        )
    return items


def cp_nav_item_is_current(request_path: str, item_url: str) -> bool:
    """Highlight control-plane sidebar links when path matches or is under changelist."""
    p = (request_path or "").split("?", 1)[0].rstrip("/") or "/"
    u = (item_url or "").split("?", 1)[0].rstrip("/")
    if not u:
        return False
    if p == u:
        return True
    if u.startswith("/admin/") and p.startswith(u):
        return True
    if u.startswith("/studio/") and p.startswith(u):
        return True
    if u.startswith("/super/") and p.startswith(u):
        return True
    return False


def is_manager_platform_admin_path(path: str) -> bool:
    """True on manager-host Django platform admin routes (/admin/*)."""
    p = (path or "").split("?", 1)[0]
    return p == "/admin" or p.startswith("/admin/")


def _append_manager_admin_nav_link(
    links: list[dict],
    *,
    spec: dict,
    urlconf: str,
    request_path: str,
) -> None:
    url = _safe_reverse(spec["url_name"], urlconf=urlconf)
    if not url:
        return
    links.append(
        {
            "id": spec["id"],
            "label": spec["label"],
            "url": url,
            "icon": spec["icon"],
            "is_current": cp_nav_item_is_current(request_path, url),
        }
    )


def build_manager_platform_admin_nav(request):
    """
    Context for manager ``/admin/*`` sidebar (not CONTROL_PLANE_NAV).

    Start + Guided setup come from ``MANAGER_UNIFIED_SIDEBAR_GROUPS``; this helper
    keeps ``quick_links`` / ``guided_links`` keys for legacy callers.
    """
    from apps.schools.manager_nav_convergence import build_manager_unified_sidebar_groups

    groups = build_manager_unified_sidebar_groups(request)
    quick_links = list(groups[0]["items"]) if groups else []
    guided_links = list(groups[1]["items"]) if len(groups) > 1 else []
    return {
        "quick_links": quick_links,
        "guided_links": guided_links,
        "groups": groups,
    }


def _primary_nav_is_current(request_path: str, item_id: str) -> bool:
    """Return True if request_path should highlight this primary nav pill."""
    p = (request_path or "").split("?", 1)[0]
    if not p.endswith("/"):
        p = p + "/"

    def _starts(*prefixes: str) -> bool:
        return any(p.startswith(pref) for pref in prefixes)

    if item_id == "primary_home":
        if p == "/super/" or p.startswith("/super/dashboard/"):
            return True
        # Platform Overview siblings (sidebar): AI consoles stay under Home pill.
        if p.startswith("/super/ai-gateway-console/"):
            return True
        if p.startswith("/super/ai-model-hub/"):
            return True
        if p.startswith("/super/global-ai-version/"):
            return True
        if p.startswith("/super/trust/"):
            return True
        if p.startswith("/super/compliance/"):
            return True
        if p.startswith("/super/operator-policy/"):
            return True
        # Tenants, provisioning, and geography — same mental model as dashboard / overview.
        return _starts(
            "/super/schools/",
            "/super/create/",
            "/super/curriculum-packs/",
            "/super/learning-delivery-packs/",
            "/super/district-enterprise/",
            "/super/geography/",
            "/super/wedge/",
            "/super/native-roster-connectors/",
            "/super/education-systems/",
            "/super/group-campuses/",
            "/super/one-sis-any-lms/",
            "/super/advancement/",
            "/super/he-pack/",
            "/super/tenants/",
            "/super/health/",
        )
    if item_id == "primary_studio":
        if p.startswith("/studio/") and not p.startswith("/studio/control/"):
            return True
        # Tenant / manager siteconfig paths aligned with Studio OS (Experience, Outputs, Launch, Automation).
        return _starts(
            "/siteconfig/theme-colors/",
            "/siteconfig/template-gallery/",
            "/siteconfig/theme-experience/",
            "/siteconfig/theme-experience/hub/",
            "/siteconfig/preview-from-form/",
            "/siteconfig/preview/toggle/",
            "/siteconfig/act-as/",
            "/siteconfig/reports/",
            "/siteconfig/customizer/",
            "/siteconfig/dashboard-hub/",
            "/siteconfig/workflow-gallery/",
            "/siteconfig/guided-onboarding/",
            "/siteconfig/support-copilot/",
            "/siteconfig/feedback-roadmap/",
            "/siteconfig/preferences/",
        )
    if item_id == "primary_operations":
        return _starts("/super/command-center/", "/super/orchestration/")
    if item_id == "primary_marketplace":
        if p.startswith("/super/marketplace/"):
            return True
        return p.startswith("/siteconfig/app-sandbox/")
    if item_id == "primary_analytics":
        return _starts(
            "/super/analytics/",
            "/super/usage/",
            "/super/pulse/",
            "/super/billing/",
            "/super/customer-success/",
        )
    if item_id == "primary_migration":
        return p.startswith("/super/migration")
    if item_id == "primary_support":
        return p.startswith("/super/support")
    if item_id == "primary_control":
        if "/studio/control/" in p:
            return True
        # Configuration Control Center + feature control (manager / tenant).
        if _starts(
            "/siteconfig/console/",
            "/siteconfig/feature-control/",
            "/siteconfig/grading-settings/",
            "/siteconfig/modules/",
            "/siteconfig/installed-packages/",
            "/siteconfig/dashboard-configuration/",
            "/siteconfig/get-blueprints/",
            "/siteconfig/sync-center/",
            "/siteconfig/school-theme/",
            "/siteconfig/tag-manager/",
            "/siteconfig/domains/",
            "/siteconfig/request-waiver/",
            "/siteconfig/request-custom-requirement/",
            "/siteconfig/maintenance/",
            "/siteconfig/impersonation-consent/",
            "/siteconfig/configuration/runtime/",
            "/siteconfig/grading-scales/region-scales/",
            "/siteconfig/regions/validation/",
            "/siteconfig/regions/comparison/",
            "/siteconfig/metadata/entity-catalog/",
            "/siteconfig/metadata/operator-hub/",
            "/siteconfig/metadata/dynamic-fields/",
            "/siteconfig/metadata/config-mutation-audit/",
        ):
            return True
        # Super governance surfaces mirrored in Control Studio outcome registry.
        return _starts(
            "/super/blueprints/",
            "/super/policies/",
            "/super/workflow-packs/",
            "/super/dashboard-packs/",
            "/super/registries/",
            "/super/metadata-catalog/",
            "/super/runtime-inspector/",
            "/super/runtime-truth-hub/",
            "/super/policy-diff/",
            "/super/workflow-simulator/",
            "/super/platform-operator-hub/",
            "/super/config/",
        )
    return False


def build_primary_control_plane_nav(request):
    """
    Horizontal primary nav (Wave 1): one product language across /super/*.
    Order: Home, Studio, Operations, Marketplace, Analytics, Migration, Support, Control.
    """
    urlconf = getattr(request, "urlconf", None) or "config.manager_urls"
    raw = [
        {
            "id": "primary_home",
            "label": "Home",
            "url_name": "super:dashboard",
            "icon": "bi-house-door",
        },
        {
            "id": "primary_studio",
            "label": "Studio",
            "url_name": "studio_os:shell",
            "icon": "bi-window-stack",
        },
        {
            "id": "primary_operations",
            "label": "Operations",
            "url_name": "super:command_center",
            "icon": "bi-lightning-charge",
        },
        {
            "id": "primary_marketplace",
            "label": "Marketplace",
            "url_name": "super:app_catalog",
            "icon": "bi-shop",
        },
        {
            "id": "primary_analytics",
            "label": "Analytics",
            "url_name": "super:analytics_overview",
            "icon": "bi-graph-up-arrow",
        },
        {
            "id": "primary_migration",
            "label": "Migration Cloud",
            "url_name": "super:migration_cloud",
            "icon": "bi-cloud-arrow-up",
        },
        {
            "id": "primary_support",
            "label": "Support",
            "url_name": "super:support_dashboard",
            "icon": "bi-headset",
        },
        {
            "id": "primary_control",
            "label": "Control",
            "url_name": "studio_os:control",
            "icon": "bi-sliders",
        },
    ]
    out = []
    path = getattr(request, "path", "") or ""
    for row in raw:
        url = _safe_reverse(
            row["url_name"],
            urlconf=urlconf,
            kwargs=row.get("kwargs"),
            args=row.get("args"),
        )
        if not url:
            continue
        out.append(
            {
                "id": row["id"],
                "label": row["label"],
                "url": url,
                "icon": row["icon"],
                "is_current": _primary_nav_is_current(path, row["id"]),
            }
        )
    # Defensive: at most ONE pill may be active. If multiple predicates fire
    # for the same URL (path overlap between primary_home and a more specific
    # surface like primary_control), prefer the MORE specific one — i.e. the
    # later item in `raw` order. Home is the broadest fallback and should
    # only win when nothing more specific matches.
    actives = [i for i, item in enumerate(out) if item["is_current"]]
    if len(actives) > 1:
        keep = actives[-1]  # most specific surface
        for i, item in enumerate(out):
            if i != keep:
                item["is_current"] = False
    return out


def _admin_primary_nav_is_current(request_path: str, item_id: str) -> bool:
    """Highlight manager /admin/ header pills (admin v1 200x preview set)."""
    p = (request_path or "").split("?", 1)[0]
    if p == "/admin":
        p = "/admin/"
    elif p and not p.endswith("/"):
        p = f"{p}/"

    def _starts(*prefixes: str) -> bool:
        return any(p.startswith(prefix) for prefix in prefixes)

    if item_id == "admin_backoffice":
        return p == "/admin/" or p.startswith("/admin/")
    if item_id == "admin_config":
        return _starts(
            "/siteconfig/console/",
            "/siteconfig/feature-control/",
            "/siteconfig/configuration/",
            "/siteconfig/grading-settings/",
            "/siteconfig/modules/",
            "/siteconfig/installed-packages/",
            "/siteconfig/dashboard-configuration/",
            "/siteconfig/get-blueprints/",
            "/siteconfig/sync-center/",
            "/siteconfig/domains/",
            "/siteconfig/metadata/",
        )
    if item_id == "admin_studio":
        return p.startswith("/studio/")
    if item_id == "admin_control_plane":
        if p.startswith("/admin/"):
            return False
        return _starts("/super/")
    if item_id == "admin_catalog":
        return _starts(
            "/super/metadata-catalog/",
            "/super/marketplace/apps/",
            "/super/marketplace/",
            "/super/registries/",
        )
    if item_id == "admin_access":
        return _starts("/super/trust/")
    if item_id == "admin_health":
        return _starts(
            "/super/tenant-health/",
            "/super/customer-success/",
            "/super/pulse/",
        )
    return False


def build_manager_platform_admin_primary_nav(request):
    """
    Horizontal primary nav for manager-host ``/admin/*`` (admin v1 200x preview).

    Distinct from ``build_primary_control_plane_nav`` (``/super/*`` product language).
    """
    urlconf = getattr(request, "urlconf", None) or "config.manager_urls"
    raw = [
        {
            "id": "admin_backoffice",
            "label": _("Backoffice"),
            "url_name": "admin:index",
            "glyph": "🏛",
        },
        {
            "id": "admin_config",
            "label": _("Config center"),
            "url_name": "siteconfig:console_domains_hub",
            "glyph": "⚙",
        },
        {
            "id": "admin_studio",
            "label": _("Studio"),
            "url_name": "studio_os:shell",
            "glyph": "⌘",
        },
        {
            "id": "admin_control_plane",
            "label": _("Control plane"),
            "url_name": "super:dashboard",
            "glyph": "↗",
        },
        {
            "id": "admin_catalog",
            "label": _("Catalog"),
            "url_name": "super:metadata_catalog",
            "glyph": "📚",
        },
        {
            "id": "admin_access",
            "label": _("Access"),
            "url_name": "super:trust_center",
            "glyph": "🔐",
        },
        {
            "id": "admin_health",
            "label": _("Health"),
            "url_name": "super:tenant_health",
            "glyph": "🩺",
        },
    ]
    path = getattr(request, "path", "") or ""
    out = []
    for row in raw:
        url = _safe_reverse(
            row["url_name"],
            urlconf=urlconf,
            kwargs=row.get("kwargs"),
            args=row.get("args"),
        )
        if not url:
            continue
        out.append(
            {
                "id": row["id"],
                "label": row["label"],
                "url": url,
                "glyph": row.get("glyph", ""),
                "icon": row.get("icon", ""),
                "is_current": _admin_primary_nav_is_current(path, row["id"]),
            }
        )
    actives = [i for i, item in enumerate(out) if item["is_current"]]
    if len(actives) > 1:
        keep = actives[-1]
        for i, item in enumerate(out):
            if i != keep:
                item["is_current"] = False
    return out


def _tenant_operator_primary_is_current(request_path: str, item_id: str) -> bool:
    """Highlight tenant operator primary pills (paths are tenant / default urlconf)."""
    p = (request_path or "").split("?", 1)[0]
    if not p.endswith("/"):
        p = p + "/"
    if item_id == "tenant_backend":
        return p.startswith("/accounts/backend") or p.startswith(
            "/authentication/backend"
        )
    if item_id == "tenant_studio":
        return p.startswith("/studio/")
    if item_id == "tenant_ccc":
        return p.startswith("/siteconfig/console/")
    if item_id == "tenant_audit":
        return p.startswith("/siteconfig/feature-control/audit/")
    if item_id == "tenant_feature":
        if p.startswith("/siteconfig/feature-control/audit/"):
            return False
        return p.startswith("/siteconfig/feature-control/")
    return False


def build_tenant_operator_primary_nav(request):
    """
    Horizontal primary nav for school operators on tenant hosts (Django admin bridge + portal).
    Only includes URLs that resolve on the active request urlconf; mirrors manager spine where applicable.
    """
    urlconf = getattr(request, "urlconf", None)
    path = getattr(request, "path", "") or ""
    raw = [
        {
            "id": "tenant_backend",
            "label": "Backend",
            "url_name": "accounts:backend_dashboard",
            "icon": "bi-grid-1x2",
        },
        {
            "id": "tenant_studio",
            "label": "Studio",
            "url_name": "studio_os:shell",
            "icon": "bi-window-stack",
        },
        {
            "id": "tenant_ccc",
            "label": "Config center",
            "url_name": "siteconfig:console_domains_hub",
            "icon": "bi-gear-wide-connected",
        },
        {
            "id": "tenant_feature",
            "label": "Feature control",
            "url_name": "siteconfig:feature_control_panel",
            "icon": "bi-sliders",
        },
        {
            "id": "tenant_audit",
            "label": "Audit",
            "url_name": "siteconfig:feature_control_audit",
            "icon": "bi-journal-check",
        },
    ]
    out = []
    for row in raw:
        url = _safe_reverse(
            row["url_name"],
            urlconf=urlconf,
            kwargs=row.get("kwargs"),
            args=row.get("args"),
        )
        if not url:
            continue
        out.append(
            {
                "id": row["id"],
                "label": row["label"],
                "url": url,
                "icon": row["icon"],
                "is_current": _tenant_operator_primary_is_current(path, row["id"]),
            }
        )
    return out


def build_control_plane_nav(request):
    """
    Return list of groups, each with "label" (optional section heading) and "items"
    (list of dicts: id, label, url, icon). Only includes items whose url resolved.
    """
    urlconf = getattr(request, "urlconf", None) or "config.manager_urls"
    request_path = getattr(request, "path", "") or ""
    groups = []

    def _finalize_group(label, resolved):
        if not resolved:
            return
        for row in resolved:
            row["is_current"] = cp_nav_item_is_current(
                request_path, row.get("url", "")
            )
        expanded = any(row.get("is_current") for row in resolved)
        groups.append({"label": label, "items": resolved, "expanded": expanded})

    def add_group(label, items):
        resolved = []
        for item in items:
            url = _safe_reverse(
                item["url_name"],
                urlconf=urlconf,
                kwargs=item.get("kwargs"),
                args=item.get("args"),
            )
            if url and item.get("query"):
                q = str(item["query"]).lstrip("?")
                url = f"{url}{'&' if '?' in url else '?'}{q}"
            if url:
                resolved.append(
                    {
                        "id": item.get("id", ""),
                        "label": item["label"],
                        "url": url,
                        "icon": item.get("icon", "bi-circle"),
                    }
                )
        _finalize_group(label, resolved)

    def add_resolved_group(label, resolved):
        _finalize_group(label, list(resolved))

    # Plan §2.1: /super nav groups — Platform Overview, Tenants, Runtime & Governance,
    # Blueprints & Policies, Workflows & Dashboards, Marketplace, Migration Cloud,
    # Providers & Integrations, Observability, Support & Success, Compliance, Billing & Usage, Platform Settings.
    add_group(
        "Platform Overview",
        [
            {
                "id": "super_dashboard",
                "label": "Dashboard",
                "url_name": "super:dashboard",
                "icon": "bi-speedometer2",
            },
            {
                "id": "super_command_center",
                "label": "Command Center",
                "url_name": "super:command_center",
                "icon": "bi-list-check",
            },
            {
                "id": "super_ai_gateway_console",
                "label": "AI gateway console",
                "url_name": "super:ai_gateway_console",
                "icon": "bi-stars",
            },
            {
                "id": "ai_center",
                "label": "AI Center",
                "url_name": "siteconfig:ai_center",
                "icon": "bi-stars",
            },
        ],
    )
    add_group(
        "Studio OS",
        [
            {
                "id": "studio_os_shell",
                "label": "Studio home",
                "url_name": "studio_os:shell",
                "icon": "bi-grid-3x3-gap",
            },
            {
                "id": "studio_os",
                "label": "Studio Experience",
                "url_name": "studio_os:experience",
                "icon": "bi-palette",
            },
            {
                "id": "studio_os_control",
                "label": "Control Studio",
                "url_name": "studio_os:control",
                "icon": "bi-sliders",
            },
        ],
    )
    add_group(
        "Tenants",
        [
            {
                "id": "super_schools_list",
                "label": "Schools list",
                "url_name": "super:schools_list",
                "icon": "bi-building",
            },
            {
                "id": "super_offboarding_queue",
                "label": "Offboarding queue",
                "url_name": "super:offboarding_queue",
                "icon": "bi-door-open",
            },
            {
                "id": "super_schools_rapid_create",
                "label": "Rapid create",
                "url_name": "super:schools_rapid_create",
                "icon": "bi-lightning-charge",
            },
            {
                "id": "super_provisioning_jobs",
                "label": "Provisioning jobs",
                "url_name": "super:provisioning_jobs",
                "icon": "bi-hourglass-split",
            },
            {
                "id": "super_provision",
                "label": "Setup Studio",
                "url_name": "super:create_school_wizard",
                "icon": "bi-plus-circle",
            },
            {
                "id": "super_tenant_health",
                "label": "School Health",
                "url_name": "super:tenant_health",
                "icon": "bi-heart-pulse",
            },
            {
                "id": "super_district_enterprise",
                "label": "District & enterprise",
                "url_name": "super:district_enterprise",
                "icon": "bi-buildings",
            },
        ],
    )
    add_group(
        "Curriculum & region",
        [
            {
                "id": "super_curriculum_packs",
                "label": "Curriculum & region packs",
                "url_name": "super:curriculum_packs",
                "icon": "bi-book",
            },
            {
                "id": "super_geography",
                "label": "Geography",
                "url_name": "super:geography",
                "icon": "bi-globe2",
            },
            {
                "id": "super_education_systems",
                "label": "Education systems",
                "url_name": "super:education_systems",
                "icon": "bi-building-add",
            },
            {
                "id": "super_learning_delivery",
                "label": "Learning delivery & institution types",
                "url_name": "super:learning_delivery_packs",
                "icon": "bi-mortarboard",
            },
            {
                "id": "super_ministry_stubs",
                "label": "Ministry report stubs",
                "url_name": "super:ministry_report_stubs",
                "icon": "bi-file-earmark-text",
            },
        ],
    )
    add_group(
        "Runtime & Governance",
        [
            {
                "id": "super_incidents",
                "label": "Incidents",
                "url_name": "platform_incidents_console",
                "icon": "bi-exclamation-triangle",
            },
            {
                "id": "super_runtime_inspector",
                "label": "Runtime inspector",
                "url_name": "super:runtime_inspector",
                "icon": "bi-code-square",
            },
            {
                "id": "super_runtime_truth_hub",
                "label": "Runtime truth hub",
                "url_name": "super:runtime_truth_hub",
                "icon": "bi-database-check",
            },
            {
                "id": "super_wedge_index",
                "label": "Wedge index",
                "url_name": "super:wedge_index",
                "icon": "bi-grid-3x3-gap",
            },
            {
                "id": "super_workflow_simulator",
                "label": "Workflow simulator",
                "url_name": "super:workflow_simulator",
                "icon": "bi-diagram-3",
            },
            {
                "id": "super_playbook_operator_hub",
                "label": "Playbook operator hub",
                "url_name": "super:playbook_operator_hub",
                "icon": "bi-journal-bookmark",
            },
        ],
    )
    add_group(
        "Blueprints & Policies",
        [
            {
                "id": "super_registries",
                "label": "Registries",
                "url_name": "super:registries_overview",
                "icon": "bi-globe",
            },
            {
                "id": "super_metadata_catalog",
                "label": "Metadata catalog",
                "url_name": "super:metadata_catalog",
                "icon": "bi-journal-code",
            },
            {
                "id": "super_blueprints",
                "label": "Blueprints",
                "url_name": "super:blueprints_catalog",
                "icon": "bi-diagram-3",
            },
            {
                "id": "super_policies",
                "label": "Policies",
                "url_name": "super:policies_catalog",
                "icon": "bi-shield",
            },
        ],
    )
    add_group(
        "Workflows & Dashboards",
        [
            {
                "id": "super_workflow_packs",
                "label": "Workflow Packs",
                "url_name": "super:workflow_packs_catalog",
                "icon": "bi-diagram-2",
            },
            {
                "id": "super_dashboard_packs",
                "label": "Dashboard Packs",
                "url_name": "super:dashboard_packs_catalog",
                "icon": "bi-grid",
            },
        ],
    )
    add_group(
        "Marketplace",
        [
            {
                "id": "super_governance",
                "label": "Governance",
                "url_name": "super:marketplace_governance",
                "icon": "bi-shield-check",
            },
            {
                "id": "super_blueprint_marketplace",
                "label": "Blueprint marketplace",
                "url_name": "super:blueprint_marketplace",
                "icon": "bi-collection",
            },
            {
                "id": "super_app_catalog",
                "label": "App catalog",
                "url_name": "super:app_catalog",
                "icon": "bi-grid-3x3-gap",
            },
            {
                "id": "super_package_rollout",
                "label": "Package rollout",
                "url_name": "super:package_rollout",
                "icon": "bi-box-arrow-up",
            },
            {
                "id": "super_customer_success",
                "label": "Customer Success",
                "url_name": "super:customer_success_dashboard",
                "icon": "bi-graph-up-arrow",
            },
        ],
    )
    add_group(
        "Migration & Integrations",
        [
            {
                "id": "super_migration",
                "label": "Migration",
                "url_name": "super:migration_cloud",
                "icon": "bi-cloud-arrow-up",
            },
            {
                "id": "apicenter_dashboard",
                "label": "API Center",
                "url_name": "apicenter:dashboard",
                "icon": "bi-plug",
            },
            {
                "id": "super_one_sis_any_lms",
                "label": "One SIS, any LMS",
                "url_name": "super:one_sis_any_lms",
                "icon": "bi-link-45deg",
            },
        ],
    )
    add_group(
        "Observability & Billing",
        [
            {
                "id": "super_usage",
                "label": "Usage",
                "url_name": "super:usage",
                "icon": "bi-bar-chart",
            },
            {
                "id": "super_pulse",
                "label": "Pulse",
                "url_name": "super:pulse",
                "icon": "bi-activity",
            },
            {
                "id": "super_analytics",
                "label": "Analytics",
                "url_name": "super:analytics_overview",
                "icon": "bi-graph-up",
            },
            {
                "id": "super_billing",
                "label": "Billing",
                "url_name": "super:billing_dashboard",
                "icon": "bi-credit-card",
            },
        ],
    )
    add_group(
        "Support & Success",
        [
            {
                "id": "super_support",
                "label": "Support",
                "url_name": "super:support_dashboard",
                "icon": "bi-headset",
            },
            {
                "id": "super_support_csat",
                "label": "CSAT",
                "url_name": "super:support_csat_dashboard",
                "icon": "bi-emoji-smile",
            },
        ],
    )
    add_group(
        "Trust & Compliance",
        [
            {
                "id": "super_trust_center",
                "label": "Trust center",
                "url_name": "super:trust_center",
                "icon": "bi-shield-lock",
            },
            {
                "id": "super_compliance",
                "label": "Compliance",
                "url_name": "super:compliance_overview",
                "icon": "bi-shield-check",
            },
            {
                "id": "compliance_audit_center",
                "label": "Audit center",
                "url_name": "compliance:dashboard",
                "icon": "bi-journal-text",
            },
            {
                "id": "compliance_audit_trail",
                "label": "Audit trail report",
                "url_name": "compliance_reporting:audit_trail",
                "icon": "bi-list-columns-reverse",
            },
        ],
    )
    # 2026-05-15 wave Z: split the historical 16-item "Platform settings & admin"
    # block into three intent-named groups (Operator tools / Tenant config defaults /
    # Metadata & audit) plus an Advanced footer. Each group fits on one screen when
    # expanded; the chevron-collapsed default keeps the spine browseable.
    add_group(
        "Operator tools",
        [
            {
                "id": "super_platform_operator_hub",
                "label": "Platform operator hub",
                "url_name": "super:platform_operator_hub",
                "icon": "bi-grid-3x3-gap",
            },
            {
                "id": "super_operator_policy",
                "label": "Operator policy",
                "url_name": "super:operator_policy",
                "icon": "bi-shield-check",
            },
            {
                "id": "super_operator_team_roster",
                "label": "Team & identity",
                "url_name": "super:operator_team_roster",
                "icon": "bi-people-fill",
            },
            {
                "id": "super_backlog_unlock_center",
                "label": "Backlog unlock center",
                "url_name": "super:backlog_unlock_center",
                "icon": "bi-unlock",
            },
            {
                "id": "super_fleet_governed_changes",
                "label": "Fleet governed changes",
                "url_name": "super:fleet_governed_changes",
                "icon": "bi-clipboard-check",
            },
        ],
    )
    add_group(
        "Tenant config defaults",
        [
            {
                "id": "config_console",
                "label": "Config center",
                "url_name": "siteconfig:console_domains_hub",
                "icon": "bi-gear-wide-connected",
            },
            {
                "id": "cp_tenant_runtime_hub",
                "label": "Tenant runtime & settings",
                "url_name": "siteconfig:tenant_runtime_configuration_hub",
                "icon": "bi-diagram-3",
            },
            {
                "id": "cp_theme_experience",
                "label": "Fleet theme & experience hub",
                "url_name": "siteconfig:theme_experience_hub",
                "icon": "bi-palette",
            },
            {
                "id": "cp_feature_control",
                "label": "Feature control",
                "url_name": "siteconfig:feature_control_panel",
                "icon": "bi-toggle2-on",
            },
            {
                "id": "cp_region_grading_scales",
                "label": "Region grading scales",
                "url_name": "siteconfig:region_grading_scales",
                "icon": "bi-table",
            },
        ],
    )
    add_group(
        "Metadata & audit",
        [
            {
                "id": "cp_metadata_operator_hub",
                "label": "Metadata & lineage hub",
                "url_name": "siteconfig:metadata_operator_hub",
                "icon": "bi-share",
            },
            {
                "id": "cp_entity_catalog",
                "label": "Entity catalog",
                "url_name": "siteconfig:entity_catalog_overview",
                "icon": "bi-diagram-3-fill",
            },
            {
                "id": "cp_metadata_dynamic_fields",
                "label": "Dynamic fields (EAV)",
                "url_name": "siteconfig:metadata_dynamic_fields_operator",
                "icon": "bi-input-cursor-text",
            },
            {
                "id": "cp_config_mutation_audit_evidence",
                "label": "Config mutation audit",
                "url_name": "siteconfig:config_mutation_audit_evidence",
                "icon": "bi-clipboard-data",
            },
            {
                "id": "cp_region_validation",
                "label": "Region validation",
                "url_name": "siteconfig:region_validation",
                "icon": "bi-ui-checks-grid",
            },
            {
                "id": "cp_region_comparison",
                "label": "Region comparison",
                "url_name": "siteconfig:region_comparison",
                "icon": "bi-columns-gap",
            },
        ],
    )
    add_group(
        "Voice of customer & proof",
        [
            {
                "id": "cp_public_to_product_matrix",
                "label": "Public-to-Product matrix",
                "url_name": "manager_public_to_product_matrix",
                "icon": "bi-grid-3x3-gap",
            },
            {
                "id": "cp_feature_gap_register",
                "label": "Feature gap register",
                "url_name": "manager_feature_gap_register",
                "icon": "bi-clipboard-check",
            },
            {
                "id": "cp_feedback_loop",
                "label": "Feedback loop · live usage",
                "url_name": "manager_feedback_loop",
                "icon": "bi-graph-up",
            },
            {
                "id": "cp_lane2_readiness",
                "label": "Lane-2 readiness (PSP / SOC2 / pilots)",
                "url_name": "manager_lane2_readiness",
                "icon": "bi-flag",
            },
        ],
    )

    _advanced_resolved = []
    reports_url = _safe_reverse("studio_os:output", urlconf=urlconf)
    if reports_url:
        _advanced_resolved.append(
            {
                "id": "cp_report_library",
                "label": "Platform Studio · Reports",
                "url": f"{reports_url}?pane=reports",
                "icon": "bi-journal-text",
            }
        )
    _advanced_resolved.extend(_platform_admin_bridge_nav_items_direct(urlconf=urlconf))
    if _advanced_resolved:
        for row in _advanced_resolved:
            row["is_current"] = cp_nav_item_is_current(
                request_path, row.get("url", "")
            )
        groups.append(
            {
                "label": "Advanced",
                "items": _advanced_resolved,
                "expanded": True,
            }
        )

    return groups


def is_manager_studio_focus_path(path: str) -> bool:
    """True when the request is a manager-host Studio OS route (focus layout)."""
    p = (path or "").split("?", 1)[0]
    return p == "/studio" or p.startswith("/studio/")


def build_studio_focus_sidebar(request) -> list[dict]:
    """
    Compact manager sidebar for /studio/* — sole vertical nav on manager Studio.

    Work modes live here only (inner studio-os__rail is suppressed on manager).
    Control governance links fold into this rail on /studio/control/ instead of
    a third column inside the canvas.
    """
    from django.utils.translation import gettext as _

    urlconf = getattr(request, "urlconf", None) or "config.manager_urls"
    path = getattr(request, "path", "") or ""
    try:
        from apps.studio_os.navigation import manager_studio_mode_from_path

        active_mode = manager_studio_mode_from_path(path)
    except (ImportError, AttributeError, TypeError, ValueError):
        active_mode = None
    mode_specs = [
        {
            "id": "studio_overview",
            "label": _("Studio overview"),
            "url_name": "studio_os:shell",
            "icon": "bi-grid-3x3-gap",
            "nav_section": "modes",
        },
        {
            "id": "studio_experience",
            "label": _("Experience"),
            "url_name": "studio_os:experience",
            "icon": "bi-palette",
            "nav_section": "modes",
        },
        {
            "id": "studio_automation",
            "label": _("Automation"),
            "url_name": "studio_os:automation",
            "icon": "bi-diagram-3",
            "nav_section": "modes",
        },
        {
            "id": "studio_output",
            "label": _("Outputs"),
            "url_name": "studio_os:output",
            "icon": "bi-file-earmark-text",
            "nav_section": "modes",
        },
        {
            "id": "studio_launch",
            "label": _("Launch"),
            "url_name": "studio_os:launch",
            "icon": "bi-rocket-takeoff",
            "nav_section": "modes",
        },
        {
            "id": "studio_control",
            "label": _("Control"),
            "url_name": "studio_os:control",
            "icon": "bi-sliders",
            "nav_section": "modes",
        },
    ]
    shortcut_specs = [
        {
            "id": "studio_command_center",
            "label": _("Command center"),
            "url_name": "super:command_center",
            "icon": "bi-terminal",
            "nav_section": "shortcuts",
        },
        {
            "id": "studio_schools",
            "label": _("Schools"),
            "url_name": "super:dashboard",
            "icon": "bi-building",
            "nav_section": "shortcuts",
        },
    ]

    items: list[dict] = []
    for spec in mode_specs:
        url = _safe_reverse(spec["url_name"], urlconf=urlconf)
        if url:
            items.append(
                {
                    "id": spec["id"],
                    "label": spec["label"],
                    "url": url,
                    "icon": spec.get("icon", "bi-circle"),
                    "nav_section": spec.get("nav_section", "modes"),
                    "section_label": _("Work modes"),
                }
            )

    try:
        from apps.studio_os.navigation import (
            append_manager_mode_task_sidebar,
            mark_studio_focus_mode_active,
        )

        mark_studio_focus_mode_active(items, request)
        append_manager_mode_task_sidebar(request, items)
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    if not active_mode:
        for spec in shortcut_specs:
            url = _safe_reverse(spec["url_name"], urlconf=urlconf)
            if url:
                items.append(
                    {
                        "id": spec["id"],
                        "label": spec["label"],
                        "url": url,
                        "icon": spec.get("icon", "bi-circle"),
                        "nav_section": spec.get("nav_section", "shortcuts"),
                        "section_label": _("Platform"),
                    }
                )

    return items
