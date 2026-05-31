"""v4.00.93 Wave C — six power chips on top of the v1 dock.

Each is registered with the SOT registry from ``AppConfig.ready``. They
all use ``source="registry"`` (server-rendered) or ``source="external"``
(anchor) — no DOM adoption — so the dock chrome can paint them without
any other app's template owning the source node.

Role / surface gates use the same matching the v1 chips use; super-only
chips declare ``roles=frozenset({"SUPERADMIN"})``.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from .registry import (
    ALL_SURFACES,
    SOURCE_EXTERNAL,
    SOURCE_REGISTRY,
    AssistDockSlot,
    register_slot,
)


# ---------------------------------------------------------------------------
# Translate — quick locale flip via Django's built-in set_language view.
# Rendered as an external anchor; the picker UI lives at /assist-dock/translate/.
# ---------------------------------------------------------------------------
register_slot(
    AssistDockSlot(
        id="translate",
        label=_("Translate"),
        icon="bi-translate",
        surfaces=ALL_SURFACES,
        source=SOURCE_EXTERNAL,
        href="/assist-dock/translate/",
        pinned_default=False,
        order=60,
        shortcut="g t",
        aria_keyshortcuts="g t",
        description=_("Switch the page language."),
    )
)

# ---------------------------------------------------------------------------
# Share this view — sheet with format + recipients + short link.
# ---------------------------------------------------------------------------
register_slot(
    AssistDockSlot(
        id="share-this-view",
        label=_("Share this view"),
        icon="bi-share",
        surfaces=ALL_SURFACES,
        source=SOURCE_EXTERNAL,
        href="/assist-dock/share/",
        pinned_default=False,
        order=62,
        shortcut="g s",
        aria_keyshortcuts="g s",
        description=_("Share this page as PDF / CSV / link."),
    )
)

# ---------------------------------------------------------------------------
# Theme — quick aesthetic flip; honors the existing theme-preference setter.
# ---------------------------------------------------------------------------
register_slot(
    AssistDockSlot(
        id="theme",
        label=_("Theme"),
        icon="bi-circle-half",
        surfaces=ALL_SURFACES,
        source=SOURCE_EXTERNAL,
        href="/assist-dock/theme/",
        pinned_default=False,
        order=64,
        shortcut="g d",
        aria_keyshortcuts="g d",
        description=_("Toggle light / dark / system theme."),
    )
)

# ---------------------------------------------------------------------------
# Voice — Web Speech API → command-bar dispatch. Opt-in per user pref.
# Rendered as a registry-source button so the JS handles the special UX.
# ---------------------------------------------------------------------------
register_slot(
    AssistDockSlot(
        id="voice",
        label=_("Voice"),
        icon="bi-mic",
        surfaces=ALL_SURFACES,
        source=SOURCE_REGISTRY,
        pinned_default=False,
        order=66,
        requires_feature="voice_assist",
        shortcut="g v",
        aria_keyshortcuts="g v",
        description=_("Speak a command (off by default)."),
    )
)

# ---------------------------------------------------------------------------
# Inspect — super-only RBAC / SiteSettings overlay for the current page.
# ---------------------------------------------------------------------------
register_slot(
    AssistDockSlot(
        id="inspect",
        label=_("Inspect"),
        icon="bi-bug",
        surfaces=ALL_SURFACES,
        roles=frozenset({"SUPERADMIN"}),
        source=SOURCE_EXTERNAL,
        href="/assist-dock/inspect/",
        pinned_default=False,
        order=70,
        shortcut="g i",
        aria_keyshortcuts="g i",
        description=_("Inspect RBAC + settings for this page."),
    )
)

# ---------------------------------------------------------------------------
# Presence — co-viewers on the current page. Badge counts visible peers.
# ---------------------------------------------------------------------------
register_slot(
    AssistDockSlot(
        id="presence",
        label=_("Who's here"),
        icon="bi-people",
        surfaces=ALL_SURFACES,
        source=SOURCE_EXTERNAL,
        href="/assist-dock/presence/",
        pinned_default=False,
        order=68,
        shortcut="g p",
        aria_keyshortcuts="g p",
        description=_("See other operators on this page right now."),
    )
)

# ---------------------------------------------------------------------------
# Settings — drag-to-pin prefs editor for the dock itself.
# ---------------------------------------------------------------------------
register_slot(
    AssistDockSlot(
        id="settings",
        label=_("Dock settings"),
        icon="bi-sliders",
        surfaces=ALL_SURFACES,
        source=SOURCE_EXTERNAL,
        href="/assist-dock/settings/",
        pinned_default=False,
        order=90,
        shortcut="g ,",
        aria_keyshortcuts="g ,",
        description=_("Pin, hide, and rearrange dock chips."),
    )
)

# ---------------------------------------------------------------------------
# Impersonate — super-only role-switch landing.
# ---------------------------------------------------------------------------
register_slot(
    AssistDockSlot(
        id="impersonate",
        label=_("Impersonate"),
        icon="bi-person-badge",
        surfaces=ALL_SURFACES,
        roles=frozenset({"SUPERADMIN"}),
        source=SOURCE_EXTERNAL,
        href="/assist-dock/impersonate/",
        pinned_default=False,
        order=72,
        shortcut="g x",
        aria_keyshortcuts="g x",
        description=_("Open the impersonation picker."),
    )
)
