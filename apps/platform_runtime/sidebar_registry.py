"""Sidebar SOT — collapses 5 reinvented sidebar systems into one registry.

The codebase ships 5 sidebar implementations (portal_sidebar / control_plane /
manager_platform_admin / studio_focus / Django Unfold). Each was built
independently and diverged on:

- which items appear (a role might see "Reports" in one shell, "Analytics" in
  another for the same destination)
- item ordering (Dashboard sometimes top, sometimes after Search)
- icon vocabulary (some use bi-bootstrap-icons, some emoji, some lucide)
- active-state markers (data-active vs aria-current vs CSS class)
- mobile collapse behavior (offcanvas vs slide-in vs hidden)

This module is the SOT for nav items. Each shell template renders from here so
adding an item is one change, not four. Migration is gradual — shells can opt in
via the `render_for_shell()` helper.

Items are role-scoped using the platform's role registry (`apps.platform_runtime
.role_registry`) so a parent never sees an admin item even if the shell template
forgets to gate it.
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
        roles=("PARENT", "STUDENT", "TEACHER", "ADMIN", "PROPRIETOR"),
        shells=(SHELL_PORTAL, SHELL_ADMIN),
        order=10,
    ),
    NavItem(
        key="grades",
        label="Grades",
        icon="bi-clipboard-data",
        url_name="portal:grades",
        roles=("PARENT", "STUDENT", "TEACHER"),
        shells=(SHELL_PORTAL,),
        order=20,
    ),
    NavItem(
        key="attendance",
        label="Attendance",
        icon="bi-calendar-check",
        url_name="portal:attendance",
        roles=("PARENT", "STUDENT", "TEACHER", "ADMIN"),
        shells=(SHELL_PORTAL,),
        order=30,
    ),
    NavItem(
        key="finance",
        label="Finance",
        icon="bi-wallet2",
        url_name="portal:finance",
        roles=("PARENT", "ADMIN", "PROPRIETOR"),
        shells=(SHELL_PORTAL,),
        order=40,
    ),
    NavItem(
        key="manage_school",
        label="Manage school",
        icon="bi-gear",
        url_name="accounts:backend_dashboard",
        roles=("ADMIN", "PROPRIETOR"),
        shells=(SHELL_PORTAL, SHELL_ADMIN),
        order=80,
    ),
    NavItem(
        key="operator_console",
        label="Operator console",
        icon="bi-terminal",
        url_name="schools:super_dashboard",
        roles=("PROPRIETOR",),
        shells=(SHELL_CONTROL_PLANE,),
        order=10,
    ),
    # ---- Studio Focus shell (Phase 1 migration) ------------------------------
    NavItem(
        key="studio_overview",
        label="Studio overview",
        icon="bi-grid-3x3-gap",
        url_name="studio_os:shell",
        roles=("PROPRIETOR",),
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
        roles=("PROPRIETOR",),
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
        roles=("PROPRIETOR",),
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
        roles=("PROPRIETOR",),
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
        roles=("PROPRIETOR",),
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
        roles=("PROPRIETOR",),
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
        roles=("PROPRIETOR",),
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
        roles=("PROPRIETOR",),
        shells=(SHELL_STUDIO_FOCUS,),
        order=110,
        section="shortcuts",
        urlconf="config.manager_urls",
    ),
    NavItem(
        key="marketplace",
        label="Marketplace",
        icon="bi-shop",
        url_name="marketplace:tenant_app_catalog",
        roles=("ADMIN", "PROPRIETOR"),
        shells=(SHELL_PORTAL,),
        order=60,
    ),
    NavItem(
        key="settings",
        label="Settings",
        icon="bi-sliders",
        url_name="accounts:user_profile",
        roles=("PARENT", "STUDENT", "TEACHER", "ADMIN", "PROPRIETOR"),
        shells=(SHELL_PORTAL, SHELL_ADMIN),
        order=90,
    ),
)


for _item in _SEED:
    register(_item)
