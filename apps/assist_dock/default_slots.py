"""v4.00.91 — six legacy chips lifted into the registry.

Loaded by ``AssistDockConfig.ready`` so the registry is seeded at startup
without any other app having to know about it. Each slot keeps the same
DOM source the v1 JS scanner used, so existing widget templates stay put.

The shape declared here is the SOT for what the dock surfaces by default;
Wave B+ chips register additively from their own apps.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from .registry import (
    ALL_SURFACES,
    SOURCE_DOM_ADOPT,
    SOURCE_EXTERNAL,
    SURFACE_MANAGER,
    AssistDockSlot,
    register_slot,
)


# Primary row (always pinned, ordered 10-29)
register_slot(
    AssistDockSlot(
        id="ai-copilot",
        label=_("AI Copilot"),
        icon="bi-stars",
        surfaces=ALL_SURFACES,
        source=SOURCE_DOM_ADOPT,
        adopt_selector=".ai-copilot-wrapper",
        pinned_default=True,
        order=10,
        requires_feature="enable_ai_help_assistant",
        shortcut="g a",
        aria_keyshortcuts="g a",
        description=_("Open the AI assistant for this page."),
    )
)

register_slot(
    AssistDockSlot(
        id="messages",
        label=_("Messages"),
        icon="bi-chat-dots",
        surfaces=ALL_SURFACES,
        source=SOURCE_DOM_ADOPT,
        adopt_selector=".portal-chathead",
        pinned_default=True,
        order=20,
        shortcut="g m",
        aria_keyshortcuts="g m",
        description=_("Open the messages panel."),
    )
)


# Platform Health (2026-06-03) — manager-surface chip aggregating broken
# feature-gap proofs + over-SLA backlog items into one live dock signal. The
# badge resolver (default_badges.platform_health_badge_resolver) paints a pill
# only when there is a problem (and only for staff). External-source so the JS
# renders a real navigable <a>; href is the manager-host mount of the platform
# health center (platform_runtime is mounted at /platform-runtime/ on the
# manager urlconf, and this chip only renders on SURFACE_MANAGER, so the path
# is stable for the surface it appears on).
register_slot(
    AssistDockSlot(
        id="platform-health",
        label=_("Platform health"),
        icon="bi-clipboard2-pulse",
        surfaces=frozenset({SURFACE_MANAGER}),
        source=SOURCE_EXTERNAL,
        href="/platform-runtime/platform-health/",
        pinned_default=True,
        order=28,
        description=_("Broken feature proofs and over-SLA backlog items."),
    )
)


# Secondary tray (collapsed under "+" by default, ordered 30-79)
register_slot(
    AssistDockSlot(
        id="feedback",
        label=_("Page feedback"),
        icon="bi-chat-heart",
        surfaces=ALL_SURFACES,
        source=SOURCE_DOM_ADOPT,
        adopt_selector=".voc-widget",
        pinned_default=False,
        order=30,
        shortcut="g f",
        aria_keyshortcuts="g f",
        description=_("Share quick feedback about this page."),
    )
)

register_slot(
    AssistDockSlot(
        id="help",
        label=_("Help on this page"),
        icon="bi-question-circle",
        surfaces=ALL_SURFACES,
        source=SOURCE_DOM_ADOPT,
        adopt_selector="[data-rmc-page-help]",
        pinned_default=False,
        order=40,
        # `?` chord intentionally omitted — owned globally by the kbd cheatsheet
        # opener (rmc-shortcuts-runtime.js + rmc-kbd-cheatsheet.js). Publishing
        # it here too would advertise a chord that races the cheatsheet handler
        # and silently fails when the chip is hidden. v4.01.03 phantom-shortcut
        # audit stripped it to keep aria-keyshortcuts honest.
        description=_("Open contextual help for this page."),
    )
)

register_slot(
    AssistDockSlot(
        id="context",
        label=_("Context"),
        icon="bi-info-circle",
        surfaces=ALL_SURFACES,
        source=SOURCE_DOM_ADOPT,
        adopt_selector=".cp-context-drawer-toggle",
        pinned_default=False,
        order=50,
        # `g c` chord intentionally omitted — overlaps control-plane Command
        # Center (control_plane_base-1.js shortcuts['c']) and tenant Configure
        # (rmc-shortcuts-runtime.js goNav("configure")). Both are real bindings;
        # publishing the same chord here would let the assist-dock chip win
        # navigation away from the user's intended destination on one surface
        # while losing on another. v4.01.03 phantom-shortcut audit stripped it.
        description=_("Open the page context drawer."),
    )
)


# Trailing utility — back-to-top stays in its own corner aesthetic via CSS,
# but is declared here so the registry is complete.
register_slot(
    AssistDockSlot(
        id="back-to-top",
        label=_("Back to top"),
        icon="bi-arrow-up-short",
        surfaces=ALL_SURFACES,
        source=SOURCE_DOM_ADOPT,
        adopt_selector="#back-to-top-btn",
        pinned_default=False,
        order=80,
        aria_keyshortcuts="Home",
        description=_("Scroll back to the top of the page."),
    )
)
