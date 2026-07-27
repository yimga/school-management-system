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
    FAMILY_PORTAL_ROLES,
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
        # `g s` chord intentionally omitted — control_plane_base-1.js binds
        # `g s` to /super/support/. Letting the assist-dock chip claim the
        # same chord on the control-plane surface would steal navigation
        # away from Support; on portal/tenant the chord is unclaimed but
        # for SOT consistency we keep this off entirely. v4.01.03 phantom
        # audit (path B).
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
        # `g d` chord intentionally omitted — control_plane_base-1.js binds
        # `g d` to /super/ (Dashboard). v4.01.03 phantom audit stripped it
        # to keep the cross-surface chord catalog honest.
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
        # `g v` chord intentionally omitted — chip only renders when the
        # voice_assist feature flag is on, so the advertised chord would
        # silently fail for every operator who hasn't opted in. v4.01.03
        # phantom audit stripped it.
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
        # `g i` chord intentionally omitted — SUPERADMIN-only chip is hidden
        # for the vast majority of operators, so advertising the chord
        # platform-wide would publish a phantom on every non-super session.
        # v4.01.03 phantom audit stripped it.
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
        # Operator/staff co-presence ("other operators on this page"). Not a
        # family-surface concept — hidden from parents/students/employers.
        hidden_for_roles=FAMILY_PORTAL_ROLES,
        source=SOURCE_EXTERNAL,
        href="/assist-dock/presence/",
        pinned_default=False,
        order=68,
        # `g p` chord intentionally omitted — control_plane_base-1.js binds
        # `g p` to /super/pulse/. v4.01.03 phantom audit stripped it to
        # avoid cross-surface chord conflict.
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
        # `g x` chord intentionally omitted — SUPERADMIN-only chip is hidden
        # for non-super sessions, so the advertised chord would be a phantom
        # for every regular operator. v4.01.03 phantom audit stripped it.
        description=_("Open the impersonation picker."),
    )
)
