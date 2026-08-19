"""Sidebar SOT for **Studio focus** rails only.

Portal and operator live membership is NOT this module. Those rails are:

- tenant: ``apps.siteconfig.portal_sidebar_items``
- operator: ``apps.schools.control_plane_nav`` + ``manager_nav_convergence``
- new spine rows: ``apps.platform_runtime.nav_engine``

``for_shell(SHELL_STUDIO_FOCUS)`` is the only production consumer. Portal seed
rows below (grades/attendance/finance) use url_names that do not exist; they
are not rendered on the live tenant rail.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# Shell identifiers — match the base template file basename.
SHELL_PORTAL = "portal"  # templates/portal_base.html
SHELL_CONTROL_PLANE = "control_plane"  # templates/control_plane_skeleton.html
SHELL_ADMIN = "admin"  # templates/admin/base_site.html
SHELL_MARKETING = "marketing"  # templates/marketing/base_marketing.html
SHELL_STUDIO_FOCUS = "studio_focus"  # templates/studio_os/shell_control_plane.html


@dataclass(frozen=True)
class NavItem:
    key: str  # stable identifier; used as nav item id + a11y target
    label: str  # display label (must be `_()` lazy-translatable at call site)
    icon: str  # bootstrap-icons class, e.g. "bi-house"
    url_name: str  # Django URL name, resolved via {% url %}
    roles: tuple[str, ...]  # role codes that may see this item
    shells: tuple[str, ...]  # shells that should render this item
    order: int  # sort order within the shell — lower = higher in the list
    children: tuple["NavItem", ...] = field(default_factory=tuple)
    badge_context_key: str | None = None  # optional context key for badge count
    section: str = ""  # group label, e.g. "modes" | "shortcuts" | "mode_tasks"
    urlconf: str = ""  # optional Django urlconf override (manager_urls etc.)


_REGISTRY: list[NavItem] = []


def register(item: NavItem) -> None:
    """Add a nav item to the registry. Last-wins on same key for hot-reload."""
    global _REGISTRY
    _REGISTRY = [existing for existing in _REGISTRY if existing.key != item.key]
    _REGISTRY.append(item)


def all_items() -> tuple[NavItem, ...]:
    return tuple(_REGISTRY)


def for_shell(shell: str, role_codes: Iterable[str]) -> list[NavItem]:
    """Items that should render on the given shell for the given user roles."""
    role_set = set(role_codes)
    matched = [
        item
        for item in _REGISTRY
        if shell in item.shells and (not item.roles or role_set & set(item.roles))
    ]
    matched.sort(key=lambda it: (it.order, it.key))
    return matched


# ---------------------------------------------------------------------------
# Initial seed — the four shells' overlapping top-level items, consolidated.
# Bare-minimum to prove the SOT contract; individual shells migrate items into
# the registry as they're touched in subsequent waves.
# ---------------------------------------------------------------------------

_SEED: tuple[NavItem, ...] = (
    NavItem(
        key="dashboard",
        label="Dashboard",
        icon="bi-house-door",
        url_name="portal:home",
        roles=("PARENT", "STUDENT", "TEACHER", "ADMIN", "PROPRIETOR"),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_PORTAL, SHELL_ADMIN),
        order=10,
    ),
    # NOTE (nav-migration gap): the next three portal items use generic
    # url_names (portal:grades / portal:attendance / portal:finance) that do NOT
    # exist — Grades/Attendance/Finance are role-specific (student vs teacher vs
    # parent), so a single route can't serve roles=(PARENT,STUDENT,TEACHER).
    # No live surface renders these today (the only for_shell() consumer pulls
    # SHELL_STUDIO_FOCUS, and the live tenant portal nav comes from
    # apps/siteconfig/portal_sidebar_items.py with correct role-specific routes),
    # so they are safely dropped (_safe_reverse). Before wiring SHELL_PORTAL to
    # this registry, replace these with role-dispatch routes (or remove as
    # superseded). Left intentionally unfabricated — a wrong route is worse.
    NavItem(
        key="grades",
        label="Grades",
        icon="bi-clipboard-data",
        url_name="portal:grades",
        roles=("PARENT", "STUDENT", "TEACHER"),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_PORTAL,),
        order=20,
    ),
    NavItem(
        key="attendance",
        label="Attendance",
        icon="bi-calendar-check",
        url_name="portal:attendance",
        roles=("PARENT", "STUDENT", "TEACHER", "ADMIN"),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_PORTAL,),
        order=30,
    ),
    NavItem(
        key="finance",
        label="Finance",
        icon="bi-wallet2",
        url_name="portal:finance",
        roles=("PARENT", "ADMIN", "PROPRIETOR"),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_PORTAL,),
        order=40,
    ),
    NavItem(
        key="manage_school",
        label="Manage school",
        icon="bi-gear",
        url_name="accounts:backend_dashboard",
        roles=("ADMIN", "PROPRIETOR"),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_PORTAL, SHELL_ADMIN),
        order=80,
    ),
    NavItem(
        key="operator_console",
        label="Operator console",
        icon="bi-terminal",
        url_name="super:dashboard",  # was schools:super_dashboard (no such route) — operator landing is super:dashboard
        roles=("PROPRIETOR",),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_CONTROL_PLANE,),
        order=10,
    ),
    # ---- Studio Focus shell (Phase 1 migration) ------------------------------
    NavItem(
        key="studio_overview",
        label="Studio overview",
        icon="bi-grid-3x3-gap",
        url_name="studio_os:shell",
        roles=("PROPRIETOR",),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_STUDIO_FOCUS,),
        order=10,
        section="modes",
        urlconf="config.manager_urls",
    ),
    NavItem(
        key="studio_experience",
        label="Experience",
        icon="bi-palette",
        url_name="studio_os:experience",
        roles=("PROPRIETOR",),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_STUDIO_FOCUS,),
        order=20,
        section="modes",
        urlconf="config.manager_urls",
    ),
    NavItem(
        key="studio_automation",
        label="Automation",
        icon="bi-diagram-3",
        url_name="studio_os:automation",
        roles=("PROPRIETOR",),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_STUDIO_FOCUS,),
        order=30,
        section="modes",
        urlconf="config.manager_urls",
    ),
    NavItem(
        key="studio_output",
        label="Outputs",
        icon="bi-file-earmark-text",
        url_name="studio_os:output",
        roles=("PROPRIETOR",),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_STUDIO_FOCUS,),
        order=40,
        section="modes",
        urlconf="config.manager_urls",
    ),
    NavItem(
        key="studio_launch",
        label="Launch",
        icon="bi-rocket-takeoff",
        url_name="studio_os:launch",
        roles=("PROPRIETOR",),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_STUDIO_FOCUS,),
        order=50,
        section="modes",
        urlconf="config.manager_urls",
    ),
    NavItem(
        key="studio_control",
        label="Control",
        icon="bi-sliders",
        url_name="studio_os:control",
        roles=("PROPRIETOR",),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_STUDIO_FOCUS,),
        order=60,
        section="modes",
        urlconf="config.manager_urls",
    ),
    NavItem(
        key="studio_command_center",
        label="Command center",
        icon="bi-terminal",
        url_name="super:command_center",
        roles=("PROPRIETOR",),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_STUDIO_FOCUS,),
        order=100,
        section="shortcuts",
        urlconf="config.manager_urls",
    ),
    NavItem(
        key="studio_schools",
        label="Schools",
        icon="bi-building",
        url_name="super:dashboard",
        roles=("PROPRIETOR",),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_STUDIO_FOCUS,),
        order=110,  # magic-number-allow: display-sort-order-value
        section="shortcuts",
        urlconf="config.manager_urls",
    ),
    NavItem(
        key="marketplace",
        label="Marketplace",
        icon="bi-shop",
        url_name="siteconfig:module_market",  # was marketplace:tenant_app_catalog (no such route) — tenant marketplace is siteconfig:module_market
        roles=("ADMIN", "PROPRIETOR"),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_PORTAL,),
        order=60,
    ),
    NavItem(
        key="settings",
        label="Settings",
        icon="bi-sliders",
        url_name="accounts:user_profile",
        roles=("PARENT", "STUDENT", "TEACHER", "ADMIN", "PROPRIETOR"),  # role-string-allow: nav-item-role-membership-tuple
        shells=(SHELL_PORTAL, SHELL_ADMIN),
        order=90,
    ),
)


for _item in _SEED:
    register(_item)
