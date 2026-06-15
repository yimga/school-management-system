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
        if fp in FOOTER_PARTIALS.values() and "marketing" not in fp.lower():
            footer_partial = fp

    return {
        "PORTAL_HEADER_VARIANT": header_variant,
        "PORTAL_FOOTER_VARIANT": header_variant,
        "PORTAL_FOOTER_PARTIAL": footer_partial,
        "PORTAL_CHROME_LAYOUT": layout,
    }


def resolve_dashboard_pack_for_request(request: Any) -> Any | None:
    """Effective DashboardPack for the request (honors per-user choice + role bucketing).

    Delegates to the shared resolver so chrome on EVERY shell follows the same precedence
    chain (per-user choice → TenantLayoutAssignment → DashboardPackAssignment → default).
    """
    try:
        from apps.siteconfig.dashboard_pack_resolver import (
            resolve_effective_template_cached,
        )
        from apps.siteconfig.models_dashboard import DashboardPack

        code = (resolve_effective_template_cached(request).get("pack_code") or "").strip()
        if code:
            return DashboardPack.objects.filter(code=code, is_active=True).first()
    except Exception:
        return None
    return None


def resolve_dashboard_template_for_request(request: Any) -> Any | None:
    """Effective DashboardTemplate for the request (honors per-user choice + role bucketing).

    Delegates to the shared resolver (resolve_effective_template) so the per-user pack
    switcher and fine→coarse role bucketing drive header/footer chrome on all portal
    shells, not just the school-level TenantLayoutAssignment for the exact role string.
    """
    try:
        from apps.siteconfig.dashboard_pack_resolver import (
            resolve_effective_template_cached,
        )

        return resolve_effective_template_cached(request).get("template")
    except Exception:
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
