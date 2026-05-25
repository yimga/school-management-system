"""
Unified manager sidebar nav model — single SOT for /admin/* and /super/* (batch 1499).

Start + Guided setup groups render from one spec on both surfaces; domain-specific
groups (CP registry, admin app catalog) remain surface-specific below the fold.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.schools.control_plane_nav import _append_manager_admin_nav_link


def manager_nav_convergence_specs():
    """Cross-surface Start group — platform backoffice ↔ control plane ↔ help ↔ config."""
    return (
        {
            "id": "nav_platform_backoffice",
            "label": _("Platform backoffice"),
            "url_name": "admin:index",
            "icon": "bi-grid-3x3-gap",
        },
        {
            "id": "nav_control_plane",
            "label": _("Control plane"),
            "url_name": "super:dashboard",
            "icon": "bi-speedometer2",
        },
        {
            "id": "nav_help_center",
            "label": _("Help center"),
            "url_name": "manager_help_center",
            "icon": "bi-question-circle",
        },
        {
            "id": "nav_config_center",
            "label": _("Config center"),
            "url_name": "siteconfig:console_domains_hub",
            "icon": "bi-gear-wide-connected",
        },
    )


def manager_guided_setup_specs():
    """Guided setup group — shared on admin and control-plane sidebars."""
    return (
        {
            "id": "super_platform_operator_hub",
            "label": _("Platform operator hub"),
            "url_name": "super:platform_operator_hub",
            "icon": "bi-diagram-3",
        },
        {
            "id": "configuration_center",
            "label": _("Configuration engine"),
            "url_name": "configuration:center",
            "icon": "bi-sliders",
        },
        {
            "id": "studio_shell",
            "label": _("Studio"),
            "url_name": "studio_os:shell",
            "icon": "bi-palette",
        },
        {
            "id": "feature_control",
            "label": _("Feature control"),
            "url_name": "siteconfig:feature_control_panel",
            "icon": "bi-toggles",
        },
        {
            "id": "theme_experience",
            "label": _("Theme & experience"),
            "url_name": "siteconfig:theme_colors",
            "icon": "bi-brush",
        },
    )


def manager_unified_sidebar_group_specs():
    """Ordered group definitions for the converged sidebar head."""
    return (
        {
            "group_id": "unified_start",
            "label": _("Start"),
            "items": manager_nav_convergence_specs(),
        },
        {
            "group_id": "unified_guided_setup",
            "label": _("Guided setup"),
            "items": manager_guided_setup_specs(),
        },
    )


def _resolve_nav_group(request, *, group_id: str, label, item_specs: tuple) -> dict | None:
    urlconf = getattr(request, "urlconf", None) or "config.manager_urls"
    request_path = getattr(request, "path", "") or ""
    items: list[dict] = []
    for spec in item_specs:
        _append_manager_admin_nav_link(
            items, spec=spec, urlconf=urlconf, request_path=request_path
        )
    if not items:
        return None
    expanded = any(row.get("is_current") for row in items)
    return {
        "group_id": group_id,
        "label": str(label),
        "items": items,
        "expanded": expanded,
    }


def build_manager_unified_sidebar_groups(request) -> list[dict]:
    """Resolved Start + Guided setup groups for both manager sidebars."""
    groups: list[dict] = []
    for spec in manager_unified_sidebar_group_specs():
        row = _resolve_nav_group(
            request,
            group_id=spec["group_id"],
            label=spec["label"],
            item_specs=spec["items"],
        )
        if row:
            groups.append(row)
    return groups


def build_manager_nav_convergence_items(request) -> list[dict]:
    """Start group items only (backward compat for callers expecting flat list)."""
    groups = build_manager_unified_sidebar_groups(request)
    if not groups:
        return []
    return list(groups[0].get("items") or [])


def convergence_item_ids() -> frozenset[str]:
    ids: set[str] = set()
    for spec in manager_unified_sidebar_group_specs():
        for item in spec["items"]:
            ids.add(item["id"])
    return frozenset(ids)


def unified_sidebar_item_ids() -> frozenset[str]:
    return convergence_item_ids()


def build_manager_catalog_nav_groups(request) -> list[dict]:
    """Platform /admin/ catalog as sidebar groups — same tree on /super/ and /admin/."""
    from apps.schools.control_plane_nav import cp_nav_item_is_current

    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return []
    try:
        from config.admin import platform_admin_site
        from apps.siteconfig.platform_admin_catalog import build_platform_admin_catalog
    except ImportError:
        return []
    try:
        app_list = platform_admin_site.get_app_list(request)
        catalog = build_platform_admin_catalog(app_list)
    except Exception:
        return []

    request_path = getattr(request, "path", "") or ""
    groups: list[dict] = []
    for section in catalog.get("sections") or []:
        items: list[dict] = []
        title = section.get("title") or "Catalog"
        for app in section.get("apps") or []:
            app_label = (app.get("app_label") or "app").lower()
            for model in app.get("models") or []:
                admin_url = model.get("admin_url") or ""
                if not admin_url:
                    continue
                obj = (model.get("object_name") or model.get("name") or "model").lower()
                item_id = f"admin_catalog_{app_label}_{obj}".replace(".", "_")[:64]
                items.append(
                    {
                        "id": item_id,
                        "label": model.get("name") or obj,
                        "url": admin_url,
                        "icon": "bi-table",
                        "is_current": cp_nav_item_is_current(request_path, admin_url),
                    }
                )
        if not items:
            continue
        groups.append(
            {
                "group_id": f"catalog_{title.lower().replace(' ', '_')[:48]}",
                "label": str(_("Backoffice · {section}").format(section=title)),
                "items": items,
                "expanded": any(row.get("is_current") for row in items),
            }
        )
    return groups


def build_manager_complete_sidebar_groups(request) -> list[dict]:
    """Full manager sidebar: Start + Guided + control plane + admin catalog (batch 1500)."""
    from apps.schools.control_plane_nav import build_control_plane_nav

    head = build_manager_unified_sidebar_groups(request)
    body = build_control_plane_nav(request)
    tail = build_manager_catalog_nav_groups(request)
    return head + body + tail
