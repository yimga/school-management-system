"""
Resolve tenant portal header/footer chrome from ThemePack.layout and DashboardPack config.

Tenants never use the RunMyCampus corporate marketing footer — only school-scoped chrome.
"""

from __future__ import annotations

from typing import Any

# Valid partial paths under templates/ (no arbitrary paths).
FOOTER_PARTIALS: dict[str, str] = {
    "standard": "components/footer.html",
    "wide": "components/footer.html",
    "card": "components/footer.html",
    "minimal": "components/portal_footers/minimal.html",
}

HEADER_VARIANTS: dict[str, str] = {
    "STANDARD": "statement",
    "WIDE": "wide",
    "CARD": "card",
    "MINIMAL": "minimal",
}


def _normalize_layout(layout: Any) -> str:
    raw = str(layout or "STANDARD").strip().upper()
    if raw in HEADER_VARIANTS:
        return raw
    return "STANDARD"


def _chrome_schema_sources(
    *,
    dashboard_pack: Any | None = None,
    dashboard_template: Any | None = None,
) -> list[dict[str, Any]]:
    """Merge order: pack (legacy) then assigned dashboard template (canonical)."""
    sources: list[dict[str, Any]] = []
    for obj in (dashboard_pack, dashboard_template):
        if obj is None:
            continue
        schema = getattr(obj, "config_schema", None) or {}
        if isinstance(schema, dict):
            sources.append(schema)
    return sources


def resolve_portal_chrome(
    *,
    site_theme: Any | None = None,
    dashboard_pack: Any | None = None,
    dashboard_template: Any | None = None,
) -> dict[str, str]:
    """
  Return template partial path + header variant token for portal_base.html.

  ``dashboard_pack.config_schema`` may include::

      {"chrome": {"header_variant": "minimal", "footer_partial": "components/portal_footers/minimal.html"}}
    """
    layout = _normalize_layout(getattr(site_theme, "layout", None))
    header_variant = HEADER_VARIANTS[layout]
    footer_key = header_variant if header_variant in FOOTER_PARTIALS else "standard"
    footer_partial = FOOTER_PARTIALS[footer_key]

    for schema in _chrome_schema_sources(
        dashboard_pack=dashboard_pack,
        dashboard_template=dashboard_template,
    ):
        chrome = schema.get("chrome") or {}
        if not isinstance(chrome, dict):
            continue
        hv = str(chrome.get("header_variant") or "").strip().lower()
        if hv in FOOTER_PARTIALS:
            header_variant = hv
            footer_partial = FOOTER_PARTIALS[hv]
        fp = str(chrome.get("footer_partial") or "").strip()
        if fp in FOOTER_PARTIALS.values():
            footer_partial = fp

    return {
        "PORTAL_HEADER_VARIANT": header_variant,
        "PORTAL_FOOTER_VARIANT": header_variant,
        "PORTAL_FOOTER_PARTIAL": footer_partial,
        "PORTAL_CHROME_LAYOUT": layout,
    }


def resolve_dashboard_pack_for_request(request: Any) -> Any | None:
    """Active DashboardPack for request school + effective portal role, if assigned."""
    school = getattr(request, "school", None)
    user = getattr(request, "user", None)
    if not school or not user or not getattr(user, "is_authenticated", False):
        return None
    role = (getattr(user, "role", "") or "").strip()
    if not role:
        return None
    role_keys = {role, role.lower(), role.upper()}
    try:
        from apps.siteconfig.models_dashboard import DashboardPackAssignment

        assignment = (
            DashboardPackAssignment.objects.filter(
                school_id=school.pk,
                role__in=role_keys,
                is_active=True,
            )
            .select_related("dashboard_pack")
            .first()
        )
        if assignment and assignment.dashboard_pack and assignment.dashboard_pack.is_active:
            return assignment.dashboard_pack
    except Exception:
        return None
    return None


def resolve_dashboard_template_for_request(request: Any) -> Any | None:
    """Assigned DashboardTemplate for request school + user role (Configuration Center)."""
    school = getattr(request, "school", None)
    user = getattr(request, "user", None)
    if not school or not user or not getattr(user, "is_authenticated", False):
        return None
    role = (getattr(user, "role", "") or "").strip().upper()
    if not role:
        return None
    try:
        from apps.siteconfig.models_dashboard import TenantLayoutAssignment

        assignment = (
            TenantLayoutAssignment.objects.filter(
                school_id=school.pk,
                role=role,
                is_active=True,
            )
            .select_related("template")
            .first()
        )
        if assignment and assignment.template and assignment.template.is_active:
            return assignment.template
    except Exception:
        return None
    return None


def describe_portal_chrome_override(dashboard_template: Any | None) -> str:
    """Human label for operator UI (template config_schema.chrome)."""
    if dashboard_template is None:
        return "theme_pack_default"
    schema = getattr(dashboard_template, "config_schema", None) or {}
    if not isinstance(schema, dict):
        return "theme_pack_default"
    chrome = schema.get("chrome") or {}
    if not isinstance(chrome, dict):
        return "theme_pack_default"
    hv = str(chrome.get("header_variant") or "").strip().lower()
    if hv in FOOTER_PARTIALS:
        return hv
    fp = str(chrome.get("footer_partial") or "").strip()
    if fp in FOOTER_PARTIALS.values():
        for key, path in FOOTER_PARTIALS.items():
            if path == fp:
                return key
    return "theme_pack_default"
