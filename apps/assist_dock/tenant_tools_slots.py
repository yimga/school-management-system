"""v4.02.8 — Tenant workspace Tools edge-tray registry extensions."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from .registry import (
    FAMILY_PORTAL_ROLES,
    SOURCE_REGISTRY,
    SURFACE_ADMIN,
    SURFACE_PORTAL,
    AssistDockSlot,
    register_slot,
)

# Tenant tools render on the portal shell AND the tenant Django /admin/ (Unfold)
# shell, which resolves to the "admin" surface — so these slots must be visible
# on both or the tenant /admin/ Tools tray loses Help center / Report issue /
# Command (the assist-dock registry island is filtered by the real surface).
_TENANT_TOOLS_SURFACES = frozenset({SURFACE_PORTAL, SURFACE_ADMIN})

register_slot(
    AssistDockSlot(
        id="tenant-kb",
        label=_("Help center"),
        icon="bi-journal-bookmark",
        surfaces=_TENANT_TOOLS_SURFACES,
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=42,
        description=_("Open the school help center and knowledge base."),
    )
)

register_slot(
    AssistDockSlot(
        id="tenant-support",
        label=_("Report issue"),
        icon="bi-life-preserver",
        surfaces=_TENANT_TOOLS_SURFACES,
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=43,
        description=_("Report a problem with this page."),
    )
)

register_slot(
    AssistDockSlot(
        id="tenant-command",
        label=_("Command"),
        icon="bi-search",
        surfaces=_TENANT_TOOLS_SURFACES,
        # Cross-entity search (students / teachers / invoices) is staff/educator
        # tooling — parents/students have their own scoped views, not a global
        # command palette. Header ⌘K search is separately gated for them.
        hidden_for_roles=FAMILY_PORTAL_ROLES,
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=44,
        description=_("Open command search (Ctrl+K)."),
    )
)
