"""
Central registry and resolver for authenticated shell / route-family metadata.

Templates may use ``rmc_shell`` (from the ``shell_contract`` context processor) to avoid
ad-hoc string duplication for audits, A/B shell tooling, and future partial extraction.

This module is **descriptive** (classification from path + host), not authorization.
Permission checks stay in views, decorators, and policy layers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Route / URL families for inventory and conformance (not Django url names).
ROUTE_FAMILIES: tuple[str, ...] = (
    "admin",
    "super",
    "studio",
    "siteconfig",
    "portal",
    "marketplace",
    "api-center",
    "metadata",
    "evals",
    "communication",
    "academics",
    "reports",
    "organization",
    "automation",
    "billing",
    "setup-studio",
    "onboard",
    "app",  # generic authenticated app area
    "public",
)

SHELL_LAYOUT_TOKENS: tuple[str, ...] = (
    "portal",
    "control-plane",
    "admin",
    "studio-os",
    "tenant-app",
    "marketing",
    "public",
)

NAV_FAMILY_TOKENS: tuple[str, ...] = (
    "portal",
    "control-plane",
    "admin",
    "studio",
    "none",
)

_PREFIX_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^/admin(?:/|$)"), "admin"),
    (re.compile(r"^/super(?:/|$)"), "super"),
    (re.compile(r"^/studio(?:/|$)"), "studio"),
    (re.compile(r"^/siteconfig(?:/|$)"), "siteconfig"),
    (re.compile(r"^/portal(?:/|$)"), "portal"),
    (re.compile(r"^/marketplace(?:/|$)"), "marketplace"),
    (re.compile(r"^/api-center(?:/|$)"), "api-center"),
    (re.compile(r"^/api/internal/metadata(?:/|$)"), "metadata"),
    (re.compile(r"^/metadata(?:/|$)"), "metadata"),
    (re.compile(r"^/evals(?:/|$)"), "evals"),
    (re.compile(r"^/communication(?:/|$)"), "communication"),
    (re.compile(r"^/academics(?:/|$)"), "academics"),
    (re.compile(r"^/reports(?:/|$)"), "reports"),
    (re.compile(r"^/organization/(?:network/)?"), "organization"),
    (re.compile(r"^/automation(?:/|$)"), "automation"),
    (re.compile(r"^/billing(?:/|$)"), "billing"),
    (re.compile(r"^/setup-studio(?:/|$)"), "setup-studio"),
    (re.compile(r"^/onboard(?:/|$)"), "onboard"),
)

_MARKETING_PREFIXES: frozenset[str] = frozenset(
    ("/", "/about", "/pricing", "/contact", "/privacy", "/terms", "/cookies")
)


@dataclass(frozen=True, slots=True)
class ShellContract:
    """Immutable shell classification for the active request."""

    route_family: str
    layout_token: str
    host_kind: str
    nav_family: str
    main_region: str


def _route_family_from_path(path: str) -> str:
    p = path or "/"
    for pattern, fam in _PREFIX_RULES:
        if pattern.search(p):
            return fam
    if p in _MARKETING_PREFIXES or p.startswith("/blog") or p.startswith("/marketing"):
        return "public"
    if p == "/" and len(p) == 1:
        return "public"
    return "app"


def _layout_and_nav(
    path: str, host_kind: str, route_family: str
) -> tuple[str, str, str]:
    """
    Return (layout_token, nav_family, main_region).
    """
    p = path or "/"
    hk = (host_kind or "school").strip().lower() or "school"

    if p.startswith("/admin/"):
        return "admin", "admin", "main"

    if hk == "manager":
        if route_family == "studio" or p.startswith("/studio/"):
            return "control-plane", "studio", "main"
        if route_family in ("super", "siteconfig", "marketplace", "app") or p.startswith(
            "/super/"
        ):
            return "control-plane", "control-plane", "main"
        return "control-plane", "control-plane", "main"

    if route_family == "studio" or p.startswith("/studio/"):
        return "studio-os", "studio", "main"

    if p.startswith("/portal/"):
        return "portal", "portal", "main"

    if route_family in (
        "siteconfig",
        "marketplace",
        "academics",
        "evals",
        "communication",
        "reports",
    ):
        return "tenant-app", "portal", "main"

    return "tenant-app", "portal", "main"


def _portal_authenticated_markers(host_kind: str) -> tuple[str, str]:
    """
    Markers for ``portal_base`` wrapper (portal chrome on tenant or manager-embedded).
    """
    hk = (host_kind or "school").strip().lower() or "school"
    if hk == "manager":
        return "manager-embedded", "manager-control-plane"
    return "tenant-portal", "tenant-portal"


def _studio_os_data_shell_host(host_kind: str) -> str:
    return "control-plane" if (host_kind or "school").strip().lower() == "manager" else "tenant"


def manager_header_hide_config_chip(path: str) -> bool:
    """
    Hide the CCC Config shortcut in the manager topbar when the operator is in
    Studio or Operations primary-nav zones (topology separation).
    """
    from apps.schools.control_plane_nav import _primary_nav_is_current

    p = path or "/"
    return _primary_nav_is_current(p, "primary_studio") or _primary_nav_is_current(
        p, "primary_operations"
    )


def resolve_shell_contract(request) -> dict[str, Any]:
    """
    Build a template-friendly dict for the ``rmc_shell`` context variable.
    """
    path = getattr(request, "path", None) or "/"
    try:
        host_kind = str(getattr(request, "public_host_kind", None) or "school")
    except Exception:
        host_kind = "school"
    route_family = _route_family_from_path(path)
    layout_token, nav_family, main_region = _layout_and_nav(path, host_kind, route_family)
    c = ShellContract(
        route_family=route_family,
        layout_token=layout_token,
        host_kind=host_kind,
        nav_family=nav_family,
        main_region=main_region,
    )
    wrap, surface = _portal_authenticated_markers(host_kind)
    return {
        "route_family": c.route_family,
        "layout_token": c.layout_token,
        "host_kind": c.host_kind,
        "nav_family": c.nav_family,
        "main_region": c.main_region,
        "contract": c,
        # Manager / control-plane chrome (product label; keep single source for 1008+ sweeps).
        # Title + subtitle split so the brand-mark lockup can show
        # "RunMyCampus" (title) + "Manager" (uppercase eyebrow). Both consume
        # SITE-level overrides via the resolver so a tenant rebrand stays
        # honored; defaults below keep the platform baseline.
        "control_plane_product_title": "RunMyCampus Manager",
        "control_plane_product_subtitle": "Manager",
        # HTML / sidebar tokens (1011; descriptive only, safe template fallbacks)
        "portal_shell_root": "portal",
        "portal_default_document_title": "Portal",
        "shell_sidebar_control_plane": "control-plane",
        # Breadcrumb row data-shell-chrome-breadcrumb-surface (1012)
        "tenant_portal_breadcrumb_surface": "tenant-portal",
        "control_plane_breadcrumb_surface": "control-plane",
        # Studio OS rail / nav markers (1014)
        "studio_os_sidebar_token": "studio-rail",
        # Portal (``portal_base``) chrome — replaces inline ``public_host_kind`` conditionals
        "portal_wrap_authenticated_shell": wrap,
        "authenticated_surface": surface,
        # Control-plane layout root (``control_plane_base``)
        "cp_layout_authenticated_shell": "manager-control-plane",
        # Studio OS data-* hooks (``shell.html`` / ``shell_control_plane.html``)
        "shell_data_studio_host": _studio_os_data_shell_host(host_kind),
        # Manager topbar: suppress Config chip in Studio / Operations work zones.
        "manager_header_hide_config_chip": (
            host_kind == "manager" and manager_header_hide_config_chip(path)
        ),
    }


def resolve_shell_dataclass(request) -> ShellContract:
    """Return the frozen dataclass (for tests and Python callers)."""
    d = resolve_shell_contract(request)
    return d["contract"]
