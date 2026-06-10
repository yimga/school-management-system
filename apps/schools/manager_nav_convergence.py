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
    """Manager sidebar, split by the surface that renders it.

    The shared Start + Guided head crosses both surfaces (it's how an operator
    moves between them). Below the head the spine is scoped to what the surface
    actually renders:

    * manager ``/admin/*`` (configuration) → ``config`` control-plane groups +
      the Django admin model catalog (configuration lives where the models do).
    * ``/super/*`` (day-to-day operations) → ``ops`` control-plane groups only;
      the model-catalog firehose is intentionally dropped so the operator's
      day-to-day spine stays focused.
    """
    from apps.schools.control_plane_nav import (
        build_control_plane_nav,
        is_manager_platform_admin_path,
    )

    is_admin_surface = is_manager_platform_admin_path(getattr(request, "path", "") or "")

    # Build the full registry once; each group carries its surface + an `expanded`
    # flag that is True when the current path lands on one of its items.
    all_cp = build_control_plane_nav(request)

    # The spine follows the page, not just the host shell: many configuration
    # tools are served under /super/* (e.g. /super/blueprints/, /super/operator-policy/),
    # so a pure /admin/-vs-/super/ split would strand them under the ops spine with
    # no matching nav item. Pick the surface of the group the current path lands in;
    # fall back to the host-shell default (config on /admin/, ops elsewhere).
    active = next((g for g in all_cp if g.get("expanded")), None)
    if is_admin_surface:
        surface = "config"
    elif active is not None:
        surface = active.get("surface", "ops")
    else:
        surface = "ops"

    body = [g for g in all_cp if g.get("surface") == surface]
    head = build_manager_unified_sidebar_groups(request)
    # The Django admin model catalog is /admin/-only chrome regardless of which
    # config tool surfaced the config spine.
    tail = build_manager_catalog_nav_groups(request) if is_admin_surface else []
    return _dedupe_complete_sidebar_groups(head + body + tail)


def _dedupe_complete_sidebar_groups(groups: list[dict]) -> list[dict]:
    """
    Keep the complete sidebar compact when control-plane groups and admin-catalog
    sections share labels. The first group keeps its placement; later groups with
    the same label append only unseen item ids.
    """
    merged: list[dict] = []
    label_index: dict[str, int] = {}
    seen_group_ids: set[str] = set()
    for group in groups:
        label = str(group.get("label") or "").strip()
        group_id = str(group.get("group_id") or "").strip()
        key = label.casefold() or group_id.casefold()
        if not key:
            continue
        if group_id and group_id in seen_group_ids:
            continue
        if group_id:
            seen_group_ids.add(group_id)
        if key not in label_index:
            clone = dict(group)
            clone["items"] = _dedupe_complete_sidebar_items(group.get("items") or [])
            if clone["items"]:
                label_index[key] = len(merged)
                merged.append(clone)
            continue
        target = merged[label_index[key]]
        existing = {
            str(item.get("id") or item.get("url") or item.get("label") or "").casefold()
            for item in target.get("items") or []
        }
        appended = []
        for item in group.get("items") or []:
            item_key = str(item.get("id") or item.get("url") or item.get("label") or "").casefold()
            if not item_key or item_key in existing:
                continue
            existing.add(item_key)
            appended.append(item)
        if appended:
            target["items"] = list(target.get("items") or []) + appended
            target["expanded"] = bool(target.get("expanded") or group.get("expanded"))
    return merged


def _dedupe_complete_sidebar_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in items:
        key = str(item.get("id") or item.get("url") or item.get("label") or "").casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
