"""v4.02.0 — Operator Tools edge-tray registry extensions.

Registers tray-native utilities (notebook, shortcuts, section nav, incidents,
security posture, live activity, cursors) alongside the v1 dock chips.
Rendered inside the horizontal Tools tray on manager / control-plane surfaces.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from .registry import (
    ALL_SURFACES,
    FAMILY_PORTAL_ROLES,
    SOURCE_EXTERNAL,
    SOURCE_REGISTRY,
    SURFACE_ADMIN,
    SURFACE_MANAGER,
    AssistDockSlot,
    register_slot,
)

# --- Primary capture ---------------------------------------------------------
register_slot(
    AssistDockSlot(
        id="operator-notebook",
        label=_("Notebook"),
        icon="bi-journal-plus",
        surfaces=frozenset({SURFACE_MANAGER, SURFACE_ADMIN}),
        source=SOURCE_REGISTRY,
        pinned_default=True,
        order=12,
        description=_("Capture operator notes and recent entries."),
    )
)

# --- Page utilities ----------------------------------------------------------
register_slot(
    AssistDockSlot(
        id="keyboard-shortcuts",
        label=_("Shortcuts"),
        icon="bi-command",
        surfaces=ALL_SURFACES,
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=35,
        description=_("Open the keyboard shortcuts cheatsheet."),
    )
)

register_slot(
    AssistDockSlot(
        id="copy-page-link",
        label=_("Copy link"),
        icon="bi-link-45deg",
        surfaces=ALL_SURFACES,
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=36,
        description=_("Copy the current page URL to the clipboard."),
    )
)

register_slot(
    AssistDockSlot(
        id="on-this-page",
        label=_("On this page"),
        icon="bi-list-ul",
        surfaces=ALL_SURFACES,
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=37,
        description=_("Jump to in-page section anchors."),
    )
)

register_slot(
    AssistDockSlot(
        id="command-search",
        label=_("Search"),
        icon="bi-search",
        surfaces=frozenset({SURFACE_MANAGER, SURFACE_ADMIN}),
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=38,
        description=_("Focus command search (Ctrl+K)."),
    )
)

# --- Operator awareness ------------------------------------------------------
register_slot(
    AssistDockSlot(
        id="platform-status",
        label=_("Platform status"),
        icon="bi-activity",
        surfaces=frozenset({SURFACE_MANAGER}),
        source=SOURCE_EXTERNAL,
        href="/status/",
        pinned_default=False,
        order=55,
        description=_("Public platform status and uptime."),
    )
)

register_slot(
    AssistDockSlot(
        id="open-incidents",
        label=_("Incidents"),
        icon="bi-bell",
        surfaces=frozenset({SURFACE_MANAGER}),
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=56,
        description=_("Open the incident console."),
    )
)

register_slot(
    AssistDockSlot(
        id="security-posture",
        label=_("Security"),
        icon="bi-shield-check",
        surfaces=ALL_SURFACES,
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=57,
        description=_("Review account security posture."),
    )
)

register_slot(
    AssistDockSlot(
        id="live-activity",
        label=_("Live feed"),
        icon="bi-broadcast",
        surfaces=frozenset({SURFACE_MANAGER}),
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=58,
        description=_("Open the live activity ticker drawer."),
    )
)

register_slot(
    AssistDockSlot(
        id="live-cursors",
        label=_("Live cursors"),
        icon="bi-cursor",
        surfaces=ALL_SURFACES,
        # Co-editing presence is a staff/educator collaboration tool ("teammates");
        # family surfaces (parent/student) have no teammates to co-view with.
        hidden_for_roles=FAMILY_PORTAL_ROLES,
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=59,
        description=_("Show teammates' cursors on this page."),
    )
)
