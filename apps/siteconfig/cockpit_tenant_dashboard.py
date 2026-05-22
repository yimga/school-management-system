"""Cockpit tenant dashboard defaults — v3.56.0 (2026-05-21).

Defensive default-shape factories for the per-role tenant dashboard cockpit
sections introduced by the v3 tenant-portal preview cascade:

    cockpit.workspace_context_tenant   (sidebar-top child-context card)
    cockpit.today_snapshot              (4-KPI snapshot card row + sparklines)
    cockpit.quick_actions               (6-tile quick action grid)
    cockpit.upcoming_events             (horizontal scrolling events strip)
    cockpit.activity_timeline           (recent activity timeline)
    cockpit.achievements                (school-gradient achievements card)
    cockpit.teacher_spotlight           (italic pull-quote card)

Every helper returns a dict whose `enabled` key is ``False`` by default —
operators opt in via ``SiteSettings.cockpit_payload.*`` (admin UI lands in
a follow-up wave). The orchestrator (``apps/siteconfig/cockpit_context.py``)
integrates these returns into the per-request cockpit dict; this module is
import-only and has no Django-runtime side effects.

PII safety:
  Default factories never reach into the user / student / staff directory.
  All copy is operator-published; child / teacher names appear only when
  the operator explicitly publishes the value via SiteSettings.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _


# ============================================================
# Sidebar-top — child context (tenant variant of workspace_context)
# ============================================================


def _tenant_workspace_context_dashboard_defaults() -> dict[str, Any]:
    """Sidebar-top child context card — tenant family-portal variant.

    Distinct from ``cockpit.workspace_context`` (the manager / operator
    variant rendered by ``_workspace_context.html``). This one renders the
    sidebar-top ``.tp-child-context`` block: child name + grade + online
    dot + sibling chips + sibling-add affordance.

    Default ``enabled=False`` — operator opts in via SiteSettings and the
    family-portal hydrator that resolves the active-child context.
    """
    return {
        "enabled": False,
        "label": _("Active child"),
        "live_chip": "",  # falsy hides chip; operators may publish e.g. "✓ Live"
        "child": {
            "initials": "",
            "name": "",
            "subline": "",
            "online": True,
        },
        "stats": [],  # list[{glyph, label, tone}]; tone ∈ {"", "ok"}
        "siblings": [],  # list[{initials, label, url}]
        "siblings_label": _("Family"),
        "add_child": {
            "label": _("Add child"),
            "url": "",  # falsy hides the plus-tile
        },
    }


# ============================================================
# Canvas — today snapshot (4 KPI cards + sparklines)
# ============================================================


def _tenant_today_snapshot_defaults() -> dict[str, Any]:
    """Today snapshot — 4-KPI card row with optional polyline sparklines.

    Card schema:
        icon            str   (single glyph)
        head            str   (uppercase label e.g. "ATTENDANCE")
        value           str   (large value e.g. "Present" / "$24.50")
        label           str   (sublabel e.g. "Checked in 7:48 AM")
        spark_points    str   ("0,18 14,16 28,12 …" polyline points)
        spark_color     str   (CSS color or var() — defaults to currentColor)
        delta_text      str   (delta description)
        delta_tone      str   ("" | "success" | "warn")
    """
    return {
        "enabled": False,
        "section_label": _("Today · live"),
        "live_dot": True,
        "switch_link": {"label": "", "url": ""},
        "cards": [],
    }


# ============================================================
# Canvas — quick actions grid (6 tiles)
# ============================================================


def _tenant_quick_actions_defaults() -> dict[str, Any]:
    """Quick actions — 6-tile (or fewer) grid of primary jump-to links.

    Tile schema:
        url     str
        icon    str   (single glyph)
        title   str
        sub     str
        badge   str   (optional numeric / pill)
    """
    return {
        "enabled": False,
        "section_label": _("Quick actions"),
        "tiles": [],
    }


# ============================================================
# Canvas — upcoming events strip
# ============================================================


def _tenant_upcoming_events_defaults() -> dict[str, Any]:
    """Upcoming events strip — horizontal-scrolling event cards.

    Event schema:
        url         str
        day         str  (e.g. "21")
        month       str  (e.g. "May")
        pill_label  str  (e.g. "Today" / "5 days")
        pill_tone   str  ("" | "today" | "soon" | "info")
        title       str
        meta        str
        is_today    bool  (applies tp-event--today modifier)
    """
    return {
        "enabled": False,
        "section_label": _("Upcoming · next 14 days"),
        "view_all_link": {"label": "", "url": ""},
        "events": [],
    }


# ============================================================
# Canvas — recent activity timeline
# ============================================================


def _tenant_activity_timeline_defaults() -> dict[str, Any]:
    """Recent activity — vertical-rail timeline card.

    Item schema:
        icon        str
        tone        str   ("" | "success" | "warn" | "info")
        text_html   str   (rendered via |safe — operator-published copy only)
        text        str   (fallback when text_html absent — autoescaped)
        meta_left   str
        meta_right  str
    """
    return {
        "enabled": False,
        "title": _("Recent activity"),
        "title_suffix": "",
        "view_all_link": {"label": "", "url": ""},
        "items": [],
    }


# ============================================================
# Canvas — achievements card (school-gradient + orbital decoration)
# ============================================================


def _tenant_achievements_defaults() -> dict[str, Any]:
    """Achievements — school-gradient card with chip list.

    List schema:
        icon   str  (single glyph)
        label  str
    """
    return {
        "enabled": False,
        "title": _("Achievements"),
        "count_label": "",
        "list": [],
    }


# ============================================================
# Canvas — teacher spotlight card (italic pull-quote)
# ============================================================


def _tenant_teacher_spotlight_defaults() -> dict[str, Any]:
    """Teacher spotlight — Source Serif italic pull-quote card.

    Actions schema:
        label  str
        url    str
        glyph  str  (optional)
    """
    return {
        "enabled": False,
        "title": _("Teacher spotlight"),
        "sub": _("This week's featured staff member"),
        "avatar_initials": "",
        "teacher_name": "",
        "teacher_role": "",
        "quote": "",
        "actions": [],
    }


# ============================================================
# v3.59.x Wave A (2026-05-22) — academic-year progress bar
# ============================================================


def _year_progress_defaults() -> dict[str, Any]:
    """Academic-year progress bar — rendered above the cockpit grid.

    Mirrors v3 100x preview `.tp-year-progress` (line 595). Sits between
    the page hero/header and the cockpit section grid on every role
    landing (parent / teacher / student / backend admin).

    Schema:
        enabled       bool          # default False; operator opt-in
        label         str           # e.g. "Academic year"
        term_label    str           # e.g. "Term 2"
        percent       int 0..100    # progress fill width
        eta_label     str           # e.g. "Ends June 12"

    PII safety:
        Operator-published values only. No student-specific dates ever
        appear here — the ``eta_label`` is a school-wide academic
        calendar marker.
    """
    return {
        "enabled": False,
        "label": _("Academic year"),
        "term_label": "",
        "percent": 0,
        "eta_label": "",
    }


# ============================================================
# v3.58.x Wave 10 Agent Q — tenant activity ticker (global chrome)
# ============================================================


def _tenant_activity_ticker_defaults() -> dict[str, Any]:
    """Tenant-scoped activity ticker — global chrome variant.

    Distinct namespace from the operator/manager ``cockpit.activity_ticker``
    (which carries platform-wide events). This factory ships the per-tenant
    seed for events that are safe to surface on a school subdomain:

      * new student enrollment
      * fee payment received
      * attendance milestones (e.g. "30-day perfect attendance streak")
      * parent messages / announcements
      * scheduled system maintenance windows

    Default ``enabled=False`` so tenant operators must opt in via
    ``SiteSettings.cockpit_payload.tenant_activity_ticker.*`` (or via the
    ``atk_enabled_on_tenant`` toggle in the cockpit admin form). Sensible
    seed cards ship so the ticker renders the moment an operator flips
    enabled=True without requiring them to publish 6 individual cards first.
    """
    return {
        "enabled": False,
        # v3.60.0 (2026-05-22): tuned from 60s → 40s for a snappier feel.
        "scroll_seconds": 40,
        "live_badge_label": _("LIVE"),
        "cards": [
            {
                "icon": "🎓",
                "severity": "success",
                "text": _("New student enrolled in Year 4"),
                "timestamp": _("just now"),
            },
            {
                "icon": "💳",
                "severity": "success",
                "text": _("Fee payment received · term 2"),
                "timestamp": _("2m ago"),
            },
            {
                "icon": "⭐",
                "severity": "success",
                "text": _("Class 5B reached 30-day perfect attendance"),
                "timestamp": _("18m ago"),
            },
            {
                "icon": "💬",
                "severity": "info",
                "text": _("Parent message thread updated"),
                "timestamp": _("32m ago"),
            },
            {
                "icon": "📅",
                "severity": "info",
                "text": _("Sports day reminders sent to families"),
                "timestamp": _("1h ago"),
            },
            {
                "icon": "🛠",
                "severity": "warn",
                "text": _("Scheduled maintenance · Sunday 02:00–03:00"),
                "timestamp": _("3h ago"),
            },
        ],
    }


# ============================================================
# v3.59.x Wave B (2026-05-22) — sidebar `.ics` calendar subscribe link
# ============================================================


def _calendar_subscribe_defaults() -> dict[str, Any]:
    """Sidebar `.ics` calendar subscribe link — v3 100x preview parity.

    Renders an optional sidebar utility link allowing parents / teachers /
    students to subscribe the school calendar to their phone, Outlook, or
    Google Calendar via a standard `.ics` URL.

    Schema:
        enabled    bool   # default False; operator opt-in
        label      str    # e.g. "Subscribe calendar (.ics)"
        ics_url    str    # operator-published full URL or relative path
        help_text  str    # tooltip explaining the link

    PII safety:
        ``ics_url`` is operator-published via SiteSettings.cockpit_payload
        and serves a school-wide calendar feed — never per-student or
        per-family. The link target should be unauthenticated only if the
        operator has explicitly published a public feed.
    """
    return {
        "enabled": False,
        "label": _("Subscribe calendar (.ics)"),
        "ics_url": "",
        "help_text": _(
            "Add the school calendar to your phone, Outlook, or Google Calendar."
        ),
    }


# ============================================================
# Public API — flat key→factory mapping for the orchestrator
# ============================================================

#: Mapping of cockpit-key → defaults-factory. The orchestrator in
#: ``apps/siteconfig/cockpit_context.py`` integrates these defaults into the
#: per-request cockpit dict by calling each factory and merging the result
#: under its key.
TENANT_DASHBOARD_DEFAULTS: dict[str, Any] = {
    "workspace_context_tenant": _tenant_workspace_context_dashboard_defaults,
    "today_snapshot": _tenant_today_snapshot_defaults,
    "quick_actions": _tenant_quick_actions_defaults,
    "upcoming_events": _tenant_upcoming_events_defaults,
    "activity_timeline": _tenant_activity_timeline_defaults,
    "achievements": _tenant_achievements_defaults,
    "teacher_spotlight": _tenant_teacher_spotlight_defaults,
    "tenant_activity_ticker": _tenant_activity_ticker_defaults,
    "year_progress": _year_progress_defaults,
    "calendar_subscribe": _calendar_subscribe_defaults,
}


def build_tenant_dashboard_cockpit() -> dict[str, Any]:
    """Return a fresh dict of every tenant-dashboard cockpit section default.

    Convenience for the orchestrator + tests — calls every factory once and
    composes them into a single dict. Mutation-safe: each call returns
    independently-constructed dicts (no shared mutable state).
    """
    return {key: factory() for key, factory in TENANT_DASHBOARD_DEFAULTS.items()}


__all__ = [
    "TENANT_DASHBOARD_DEFAULTS",
    "build_tenant_dashboard_cockpit",
    "_tenant_workspace_context_dashboard_defaults",
    "_tenant_today_snapshot_defaults",
    "_tenant_quick_actions_defaults",
    "_tenant_upcoming_events_defaults",
    "_tenant_activity_timeline_defaults",
    "_tenant_achievements_defaults",
    "_tenant_teacher_spotlight_defaults",
    "_tenant_activity_ticker_defaults",
    "_year_progress_defaults",
    "_calendar_subscribe_defaults",
]
