"""
Studio OS navigation helpers — shared control governance rail + manager focus sidebar.
"""

from __future__ import annotations

from django.utils.translation import gettext as _


def _studio_rail_append(
    rail: list,
    label: str,
    viewname: str,
    *,
    embed: bool = False,
    request=None,
) -> None:
    from apps.studio_os.deep_links import resolve_studio_href, url_is_cross_origin_request

    host_kind = getattr(request, "public_host_kind", None) if request is not None else None
    if host_kind != "manager" and viewname.startswith(("super:", "admin:")):
        return
    u = resolve_studio_href(viewname, embed=embed, request=request)
    if not u:
        return
    item_embed = bool(embed)
    external = False
    if request is not None and url_is_cross_origin_request(request, u):
        external = True
        item_embed = False
        u = resolve_studio_href(viewname, embed=False, request=request) or u
    rail.append(
        {"label": label, "url": u, "embed": item_embed, "external": external}
    )


def build_control_governance_rail(request) -> list[dict]:
    """Governance links for Control mode (canvas rail on tenant; CP sidebar on manager)."""
    from apps.studio_os.deep_links import resolve_studio_href, url_is_cross_origin_request

    control_rail: list[dict] = []
    _studio_rail_append(
        control_rail,
        _("Config center"),
        "studio_os:system_config_console",
        embed=True,
        request=request,
    )
    _studio_rail_append(
        control_rail,
        _("Feature control"),
        "siteconfig:feature_control_panel",
        embed=True,
        request=request,
    )
    u_audit = resolve_studio_href(
        "siteconfig:feature_control_audit", embed=False, request=request
    )
    if u_audit:
        ext_audit = bool(request and url_is_cross_origin_request(request, u_audit))
        control_rail.append(
            {
                "label": _("Audit log"),
                "url": u_audit,
                "embed": not ext_audit,
                "external": ext_audit,
            }
        )
    _studio_rail_append(
        control_rail,
        _("Runtime inspector"),
        "super:runtime_inspector",
        embed=False,
        request=request,
    )
    _studio_rail_append(
        control_rail,
        _("Metadata governance"),
        "metadata:metadata_governance",
        embed=False,
        request=request,
    )
    _studio_rail_append(
        control_rail,
        _("Lineage & registry"),
        "metadata:metadata_lineage_graph",
        embed=True,
        request=request,
    )
    _studio_rail_append(
        control_rail,
        _("Integrations"),
        "apicenter:dashboard",
        embed=False,
        request=request,
    )
    _studio_rail_append(
        control_rail,
        _("Blueprints & policy packs"),
        "siteconfig:get_blueprints",
        embed=True,
        request=request,
    )
    _studio_rail_append(
        control_rail,
        _("Policy diff"),
        "super:policy_diff",
        embed=True,
        request=request,
    )
    _studio_rail_append(
        control_rail,
        _("Plans & entitlements"),
        "super:billing_dashboard",
        embed=True,
        request=request,
    )
    _studio_rail_append(
        control_rail,
        _("Diff / impact summary"),
        "studio_os:control_impact",
        embed=True,
        request=request,
    )
    _studio_rail_append(
        control_rail,
        _("AI cleanup suggestions"),
        "studio_os:ai_cleanup",
        embed=True,
        request=request,
    )
    return control_rail


def governance_rail_to_focus_sidebar(rail: list[dict]) -> list[dict]:
    """Map control governance rail entries to studio-focus sidebar item shape."""
    items: list[dict] = []
    for idx, entry in enumerate(rail):
        url = entry.get("url")
        if not url:
            continue
        items.append(
            {
                "id": f"studio_gov_{idx}",
                "label": entry["label"],
                "url": url,
                "icon": "bi-shield-check",
                "nav_section": "governance",
                "section_label": _("Governance"),
            }
        )
    return items


def manager_studio_mode_from_path(path: str) -> str | None:
    """Return studio mode slug from manager /studio/... path, or None for overview."""
    p = (path or "").split("?", 1)[0].rstrip("/")
    if p.endswith("/studio/control") or p == "/studio/control":
        return "control"
    if p.endswith("/studio/experience") or p == "/studio/experience":
        return "experience"
    if p.endswith("/studio/automation") or p == "/studio/automation":
        return "automation"
    if p.endswith("/studio/output") or p == "/studio/output":
        return "output"
    if p.endswith("/studio/launch") or p == "/studio/launch":
        return "launch"
    return None


def _reverse_mode_base(request, url_name: str) -> str:
    from django.urls import NoReverseMatch, reverse

    urlconf = getattr(request, "urlconf", None) or "config.manager_urls"
    try:
        return reverse(url_name, urlconf=urlconf)
    except NoReverseMatch:
        from apps.studio_os.deep_links import studio_resolve_url

        return studio_resolve_url(url_name, request=request) or ""


def _request_pane(request, default: str = "overview") -> str:
    return (getattr(request, "GET", None) or {}).get("pane", default).strip().lower() or default


def _pane_focus_items(
    request,
    *,
    base_url: str,
    pane_specs: list[tuple[str, str, str]],
    default_pane: str,
    id_prefix: str,
    icon: str = "bi-dot",
) -> list[dict]:
    if not base_url:
        return []
    active_pane = _request_pane(request, default_pane)
    items: list[dict] = []
    for pane, label, pane_icon in pane_specs:
        items.append(
            {
                "id": f"{id_prefix}_{pane}",
                "label": label,
                "url": f"{base_url}?pane={pane}",
                "icon": pane_icon,
                "pane": pane,
                "nav_section": "mode_tasks",
                "section_label": _("In this mode"),
                "active": pane == active_pane,
            }
        )
    return items


def build_launch_focus_sidebar(request) -> list[dict]:
    base = _reverse_mode_base(request, "studio_os:launch")
    specs = [
        ("overview", _("Overview"), "bi-grid"),
        ("onboarding", _("Guided onboarding"), "bi-signpost-2"),
        ("create_school", _("Create school"), "bi-building-add"),
        ("plan", _("Select plan"), "bi-credit-card"),
        ("blueprints", _("Blueprint gallery"), "bi-collection"),
        ("infrastructure", _("School infrastructure"), "bi-hdd-network"),
        ("branding", _("Import branding"), "bi-palette"),
        ("migration", _("Migration path"), "bi-arrow-left-right"),
        ("role_preview", _("Preview by role"), "bi-people"),
        ("checklist", _("Launch checklist"), "bi-list-check"),
    ]
    return _pane_focus_items(
        request,
        base_url=base,
        pane_specs=specs,
        default_pane="overview",
        id_prefix="launch",
        icon="bi-rocket-takeoff",
    )


def build_automation_focus_sidebar(request) -> list[dict]:
    base = _reverse_mode_base(request, "studio_os:automation")
    specs = [
        ("overview", _("Overview"), "bi-grid"),
        ("outcomes", _("Outcomes"), "bi-bullseye"),
        ("workflow", _("Workflow center"), "bi-bezier2"),
        ("flow_gallery", _("Flow gallery"), "bi-diagram-2"),
        ("approval", _("Approval hub"), "bi-check2-circle"),
        ("dependency", _("Dependency graph"), "bi-share"),
        ("health", _("Workflow health metrics"), "bi-heart-pulse"),
        ("conflict", _("Conflict detection"), "bi-exclamation-triangle"),
        ("staged", _("Staged activation"), "bi-layers"),
        ("replay", _("Replay / rollback"), "bi-arrow-counterclockwise"),
        ("visual_builder", _("Visual builder"), "bi-bricks"),
        ("nl_workflow", _("Natural-language workflow"), "bi-chat-quote"),
        ("simulation", _("Simulation engine"), "bi-cpu"),
    ]
    return _pane_focus_items(
        request,
        base_url=base,
        pane_specs=specs,
        default_pane="overview",
        id_prefix="automation",
        icon="bi-diagram-3",
    )


def build_output_focus_sidebar(request) -> list[dict]:
    base = _reverse_mode_base(request, "studio_os:output")
    specs = [
        ("dependency", _("Report & pack graph"), "bi-diagram-3"),
        ("reports", _("Report library & letters"), "bi-journal-text"),
        ("documents", _("Document library"), "bi-folder2-open"),
        ("builder", _("Report card builder"), "bi-card-text"),
        ("credentials", _("IDs & certificates"), "bi-person-badge"),
        ("branding", _("Branding inheritance"), "bi-palette2"),
        ("policy", _("Policy & registry"), "bi-shield-check"),
    ]
    return _pane_focus_items(
        request,
        base_url=base,
        pane_specs=specs,
        default_pane="dependency",
        id_prefix="output",
        icon="bi-file-earmark-text",
    )


def build_experience_focus_sidebar(request) -> list[dict]:
    rail: list[dict] = []
    specs = [
        (_("Theme & experience hub"), "siteconfig:theme_experience_hub", "bi-palette2"),
        (_("Theme & colors"), "siteconfig:theme_colors", "bi-palette"),
        (_("Customizer"), "studio_os:experience", "bi-brush"),
        (_("School theme"), "siteconfig:school_theme_settings", "bi-building"),
        (_("Experience packs"), "studio_os:experience_packs", "bi-box-seam"),
        (_("Import from website"), "siteconfig:brand_import_from_url", "bi-link-45deg"),
        (_("Compare"), "studio_os:experience_compare", "bi-sliders"),
        (_("AI recommendations"), "studio_os:experience_recommendations", "bi-stars"),
        (_("Theme tokens"), "studio_os:experience_theme_tokens", "bi-code-slash"),
        (_("Portal shell layouts"), "studio_os:experience_portal_shell_layouts", "bi-layout-sidebar"),
        (_("Dashboard visual packs"), "studio_os:experience_dashboard_visual_packs", "bi-grid-1x2"),
        (_("School website blocks"), "studio_os:experience_school_website_blocks", "bi-window"),
        (
            _("Communication style packs"),
            "studio_os:experience_communication_style_packs",
            "bi-chat-heart",
        ),
    ]
    path = (getattr(request, "path", "") or "").split("?", 1)[0].rstrip("/")
    items: list[dict] = []
    for idx, (label, viewname, icon) in enumerate(specs):
        before = len(rail)
        _studio_rail_append(rail, label, viewname, embed=True, request=request)
        if len(rail) <= before:
            continue
        entry = rail[-1]
        url = entry.get("url") or ""
        try:
            from urllib.parse import urlparse

            active = urlparse(url).path.rstrip("/") == path
        except (AttributeError, TypeError, ValueError):
            active = False
        items.append(
            {
                "id": f"experience_{idx}",
                "label": entry["label"],
                "url": url,
                "icon": icon,
                "nav_section": "mode_tasks",
                "section_label": _("In this mode"),
                "active": active,
            }
        )
    return items


def append_manager_mode_task_sidebar(request, items: list[dict]) -> None:
    """Append in-mode task links to manager studio-focus sidebar (replaces inner workspace rails)."""
    mode = manager_studio_mode_from_path(getattr(request, "path", "") or "")
    if mode == "control":
        items.extend(
            governance_rail_to_focus_sidebar(build_control_governance_rail(request))
        )
    elif mode == "launch":
        items.extend(build_launch_focus_sidebar(request))
    elif mode == "automation":
        items.extend(build_automation_focus_sidebar(request))
    elif mode == "output":
        items.extend(build_output_focus_sidebar(request))
    elif mode == "experience":
        items.extend(build_experience_focus_sidebar(request))


def mark_studio_focus_mode_active(items: list[dict], request) -> None:
    """Highlight the active work-mode link in the studio-focus sidebar."""
    path = (getattr(request, "path", "") or "").split("?", 1)[0].rstrip("/")
    for item in items:
        if item.get("nav_section") != "modes":
            continue
        try:
            from urllib.parse import urlparse

            item_path = urlparse(item.get("url") or "").path.rstrip("/")
            item["active"] = item_path == path
        except (AttributeError, TypeError, ValueError):
            item["active"] = False
