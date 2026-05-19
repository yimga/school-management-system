"""Theme & experience entry surfaces for tenant schools and the manager control plane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class ThemeExperienceSurface:
    key: str
    title: str
    description: str
    route_name: str = ""
    path: str = ""
    query: str = ""

    def resolve_url(self) -> str:
        if self.path:
            return self.path
        if not self.route_name:
            return ""
        try:
            base = reverse(self.route_name)
        except NoReverseMatch:
            return ""
        if self.query:
            sep = "&" if "?" in base else "?"
            return f"{base}{sep}{self.query}"
        return base


def _surface_dict(surface: ThemeExperienceSurface) -> dict[str, Any]:
    return {
        "key": surface.key,
        "title": surface.title,
        "description": surface.description,
        "url": surface.resolve_url(),
    }


def _append_surfaces(
    rows: list[dict[str, Any]], surfaces: list[ThemeExperienceSurface]
) -> None:
    for surface in surfaces:
        if surface.resolve_url():
            rows.append(_surface_dict(surface))


def build_tenant_theme_experience_surfaces() -> list[dict[str, Any]]:
    """School-scoped theme, branding, and experience tools (tenant host)."""
    rows: list[dict[str, Any]] = []
    _append_surfaces(
        rows,
        [
            ThemeExperienceSurface(
                key="theme_builder",
                title=_("Visual theme builder"),
                description=_(
                    "Shopify-grade canvas: drag sections, light/dark contrast preview, save layout."
                ),
                route_name="siteconfig:theme_builder",
            ),
            ThemeExperienceSurface(
                key="studio_experience",
                title=_("Studio — Experience mode"),
                description=_(
                    "Canonical workspace for school branding, theme packs, portals, "
                    "and governed publish flows."
                ),
                route_name="studio_os:experience",
            ),
            ThemeExperienceSurface(
                key="theme_colors",
                title=_("Theme & Experience editor"),
                description=_(
                    "Full palette studio: colors, harmony, theme packs, previews, and save."
                ),
                route_name="siteconfig:theme_colors",
                query="standalone=1",
            ),
            ThemeExperienceSurface(
                key="school_admin_theme",
                title=_("Admin & backend theme pack"),
                description=_(
                    "Staff dashboards (/admin, /backend): pick the admin theme pack for this school."
                ),
                route_name="siteconfig:school_theme_settings",
            ),
            ThemeExperienceSurface(
                key="user_preferences",
                title=_("User appearance preferences"),
                description=_("Per-user light/dark preference and related UI choices."),
                route_name="siteconfig:user_preferences",
            ),
            ThemeExperienceSurface(
                key="dashboard_hub",
                title=_("Dashboard configuration"),
                description=_("Role dashboards, widgets, and layout packs for this school."),
                route_name="siteconfig:dashboard_configuration_hub",
            ),
            ThemeExperienceSurface(
                key="experience_compare",
                title=_("Compare theme options"),
                description=_("Side-by-side comparison before publishing experience changes."),
                route_name="studio_os:experience_compare",
            ),
            ThemeExperienceSurface(
                key="experience_recommendations",
                title=_("AI experience recommendations"),
                description=_("Guided suggestions for palettes, packs, and portal polish."),
                route_name="studio_os:experience_recommendations",
            ),
            ThemeExperienceSurface(
                key="portal_shell_layouts",
                title=_("Portal shell layouts"),
                description=_("Layout packs for parent, teacher, and student portal shells."),
                route_name="studio_os:experience_portal_shell_layouts",
            ),
            ThemeExperienceSurface(
                key="school_configuration",
                title=_("School Configuration Center"),
                description=_("Full tenant-safe setup cockpit including branding and workflows."),
                route_name="school_configuration_center",
            ),
        ],
    )
    return rows


def build_platform_theme_experience_surfaces() -> list[dict[str, Any]]:
    """Operator-scoped theme, branding, and platform chrome (manager host)."""
    rows: list[dict[str, Any]] = []
    _append_surfaces(
        rows,
        [
            ThemeExperienceSurface(
                key="theme_builder",
                title=_("Visual theme builder"),
                description=_(
                    "Shopify-grade canvas: drag sections, light/dark contrast preview, save layout."
                ),
                route_name="siteconfig:theme_builder",
            ),
            ThemeExperienceSurface(
                key="studio_experience",
                title=_("Studio — Experience mode"),
                description=_(
                    "Platform operator workspace for experience rails, packs, and governed changes."
                ),
                route_name="studio_os:experience",
            ),
            ThemeExperienceSurface(
                key="theme_colors",
                title=_("Theme & Experience editor"),
                description=_(
                    "Platform-wide theme packs, staff/portal defaults, and experience fields."
                ),
                route_name="siteconfig:theme_colors",
                query="standalone=1",
            ),
            ThemeExperienceSurface(
                key="configuration_experience",
                title=_("UX/UI Experience module"),
                description=_(
                    "Platform Configuration Center module: density, packs, registries, and proof links."
                ),
                path="/configuration/experience/",
            ),
            ThemeExperienceSurface(
                key="experience_compare",
                title=_("Compare theme options"),
                description=_("Operator-side comparison before publishing platform experience."),
                route_name="studio_os:experience_compare",
            ),
            ThemeExperienceSurface(
                key="experience_recommendations",
                title=_("AI experience recommendations"),
                description=_("Operator guidance for packs, density, and portal polish."),
                route_name="studio_os:experience_recommendations",
            ),
        ],
    )
    bridge_specs = (
        (
            "platform_global_branding",
            _("Platform global branding"),
            _(
                "Logos, favicon, default theme packs, and report style defaults for the platform."
            ),
        ),
        (
            "runtime_defaults",
            _("Runtime defaults — public brand"),
            _(
                "Manager chrome colors, marketing lockup URLs, and public-surface brand tokens."
            ),
        ),
        (
            "global_brand_registry",
            _("Global brand registry"),
            _("Registry of brand tokens and experience ownership metadata."),
        ),
    )
    for key, title, description in bridge_specs:
        try:
            url = reverse("super:admin_bridge", kwargs={"bridge_key": key})
        except NoReverseMatch:
            continue
        rows.append(
            {"key": key, "title": title, "description": description, "url": url}
        )
    return rows


def resolve_operator_school_impersonation_url() -> str:
    """Tenant schools list on manager — entry point for Open as school."""
    try:
        return reverse("super:schools_list")
    except NoReverseMatch:
        return "/super/schools/"
