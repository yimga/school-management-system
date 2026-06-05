"""v4.02.8 — Tenant workspace Tools edge-tray registry extensions."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from .registry import (
    SOURCE_REGISTRY,
    SURFACE_PORTAL,
    AssistDockSlot,
    register_slot,
)

register_slot(
    AssistDockSlot(
        id="tenant-kb",
        label=_("Help center"),
        icon="bi-journal-bookmark",
        surfaces=frozenset({SURFACE_PORTAL}),
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
        surfaces=frozenset({SURFACE_PORTAL}),
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
        surfaces=frozenset({SURFACE_PORTAL}),
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=44,
        description=_("Open command search (Ctrl+K)."),
    )
)
