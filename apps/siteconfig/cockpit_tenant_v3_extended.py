"""Cockpit tenant v3 extended defaults — v3.57.0 (2026-05-21).

Defensive default-shape factories for the 10 NEW v3 tenant cockpit
sections introduced by Agent A3 of v3.57.0 (platform-wide v3 100x
tenant grammar):

    cockpit.ai_study_buddy           (per-student AI study chip — A8-wire-pending)
    cockpit.parent_teacher_thread    (inline thread + reply box)
    cockpit.realtime_presence        (classmates-online dots)
    cockpit.gradebook_trend          (rolling GPA sparkline per subject)
    cockpit.attendance_heatmap       (month-grid heatmap calendar)
    cockpit.financial_timeline       (fees + payments + balance timeline)
    cockpit.sibling_compare          (privacy-gated, opt-in)
    cockpit.life_event_timeline      (graduation / birthday / milestones)
    cockpit.calendar_weather         (school calendar + weather overlay)
    cockpit.lesson_of_day            (lesson card)

Every helper returns a dict whose ``enabled`` key is ``False`` by default —
canonical home routes opt-in via view-context overrides. The orchestrator
(``apps/siteconfig/cockpit_context.py``) calls ``build_tenant_v3_extended_cockpit``
and merges the result into the per-request cockpit dict.

PII safety:
  - Default factories NEVER reach the user / student / staff directory.
  - All copy is operator-published; child / sibling / teacher names appear only
    when the view context explicitly publishes the value.
  - Sibling-compare is gated by an explicit ``opt_in`` flag — defaults False.
  - Realtime presence renders initials only, never full names.
  - Wire to a8 by replacing the ``a8_pending`` marker in the factory return.

Brand-variance contract:
  - No hex literals here. Every CSS color routes through CSS custom properties
    on the rendering side (`var(--brand-primary)`, `var(--brand-accent)`).
  - Sparkline / heatmap fill colors default to ``currentColor`` so the
    consuming page's text color cascades correctly under any school primary.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _


# ============================================================
# 1. AI study buddy chip
# ============================================================


def _tenant_ai_study_buddy_defaults() -> dict[str, Any]:
    """Per-student AI study buddy chip — A8-wire-pending stub.

    Schema:
      enabled         bool       # default False
      label           str
      greeting        str        # operator-published copy
      suggestions     list[{icon, label, url}]   # 0..3
      wire_pending    bool       # True when AI service not yet wired
      a8_wire_pending bool       # marker — A8 owns the actual AI service call
    """
    return {
        "enabled": False,
        "label": _("Study buddy"),
        "greeting": _("Ask anything about today's lessons."),
        "suggestions": [],
        "wire_pending": True,
        "a8_wire_pending": True,
    }


# ============================================================
# 2. Parent-teacher inline thread
# ============================================================


def _tenant_parent_teacher_thread_defaults() -> dict[str, Any]:
    """Inline parent-teacher chat thread — last 5 messages + reply affordance.

    Schema:
      enabled       bool
      title         str
      teacher_name  str
      messages      list[{
                      author_initials, author_label, body, sent_iso,
                      mine: bool,
                    }]
      reply:
        url         str        # POST target (empty disables reply box)
        placeholder str
        cta         str
    """
    return {
        "enabled": False,
        "title": _("Teacher thread"),
        "teacher_name": "",
        "messages": [],
        "reply": {
            "url": "",
            "placeholder": _("Reply to teacher…"),
            "cta": _("Send"),
        },
    }


# ============================================================
# 3. Real-time presence dots
# ============================================================


def _tenant_realtime_presence_defaults() -> dict[str, Any]:
    """Real-time presence dots — classmates currently online (initials only).

    Schema:
      enabled        bool
      title          str
      online_count   int
      total_count    int
      presence       list[{initials, online: bool, tone: ""|"focus"}]
      a8_wire_pending bool     # True until websocket presence channel lands
    """
    return {
        "enabled": False,
        "title": _("Classmates online"),
        "online_count": 0,
        "total_count": 0,
        "presence": [],
        "a8_wire_pending": True,
    }


# ============================================================
# 4. Gradebook trend chart
# ============================================================


def _tenant_gradebook_trend_defaults() -> dict[str, Any]:
    """Rolling GPA / score sparkline per subject.

    Schema:
      enabled    bool
      title      str
      sub        str
      subjects   list[{
                   subject, current_value, delta_text, delta_tone,
                   spark_points,   # polyline e.g. "0,18 20,14 …"
                 }]
    """
    return {
        "enabled": False,
        "title": _("Gradebook trend"),
        "sub": _("Rolling 6 assessments"),
        "subjects": [],
    }


# ============================================================
# 5. Attendance heatmap calendar
# ============================================================


def _tenant_attendance_heatmap_defaults() -> dict[str, Any]:
    """Month-grid attendance heatmap.

    Schema:
      enabled    bool
      title      str
      month_label  str  (e.g. "May 2026")
      legend     list[{tone, label}]    # tone in {"absent","late","present","excused",""}
      cells      list[{
                   day,         # str e.g. "21"
                   tone,        # "" | "present" | "absent" | "late" | "excused" | "weekend"
                   tooltip,
                   is_today: bool,
                 }]
    """
    return {
        "enabled": False,
        "title": _("Attendance heatmap"),
        "month_label": "",
        "legend": [],
        "cells": [],
    }


# ============================================================
# 6. Financial timeline (fees + payments + balance)
# ============================================================


def _tenant_financial_timeline_defaults() -> dict[str, Any]:
    """Vertical timeline of fees, payments, balance events.

    Schema:
      enabled        bool
      title          str
      balance_display  str    (operator-formatted; never raw Decimal)
      balance_tone   str      ("" | "ok" | "warn" | "danger")
      events         list[{
                       iso,           # ISO date
                       label,
                       amount_display,
                       tone,          # "fee" | "payment" | "discount" | "balance"
                       icon,
                     }]
    """
    return {
        "enabled": False,
        "title": _("Financial timeline"),
        "balance_display": "",
        "balance_tone": "",
        "events": [],
    }


# ============================================================
# 7. Sibling comparison (privacy-gated, opt-in)
# ============================================================


def _tenant_sibling_compare_defaults() -> dict[str, Any]:
    """Sibling comparison chart — privacy-gated.

    Schema:
      enabled    bool
      opt_in     bool         # MUST be True for render — privacy gate
      title      str
      privacy_notice  str
      metrics    list[{
                   metric_label,
                   siblings: list[{initials, value_display, spark_points}],
                 }]
    """
    return {
        "enabled": False,
        "opt_in": False,
        "title": _("Sibling comparison"),
        "privacy_notice": _(
            "Opt-in family setting. Names never appear — initials only."
        ),
        "metrics": [],
    }


# ============================================================
# 8. Life-event timeline
# ============================================================


def _tenant_life_event_timeline_defaults() -> dict[str, Any]:
    """Life events: graduations, birthdays, milestones.

    Schema:
      enabled    bool
      title      str
      events     list[{
                   iso,
                   day_label,    # e.g. "23 May"
                   icon,         # glyph
                   title,
                   sub,
                   tone,         # "" | "graduation" | "birthday" | "milestone"
                 }]
    """
    return {
        "enabled": False,
        "title": _("Life events"),
        "events": [],
    }


# ============================================================
# 9. School calendar + weather overlay
# ============================================================


def _tenant_calendar_weather_defaults() -> dict[str, Any]:
    """7-day school calendar strip with weather overlay.

    Schema:
      enabled    bool
      title      str
      days       list[{
                   day_short,     # "Mon"
                   day_num,       # "21"
                   is_today: bool,
                   weather_icon,
                   temp_display,
                   event_label,   # "" if none
                 }]
    """
    return {
        "enabled": False,
        "title": _("Week ahead"),
        "days": [],
    }


# ============================================================
# 10. Lesson of the day
# ============================================================


def _tenant_lesson_of_day_defaults() -> dict[str, Any]:
    """Today's lesson card.

    Schema:
      enabled        bool
      title          str
      subject        str
      lesson_title   str
      teacher_name   str
      time_window    str    # e.g. "10:30 – 11:15"
      summary        str    # operator-published; never auto-rendered
      resources      list[{label, url, icon}]
      cta:
        label        str
        url          str
    """
    return {
        "enabled": False,
        "title": _("Lesson of the day"),
        "subject": "",
        "lesson_title": "",
        "teacher_name": "",
        "time_window": "",
        "summary": "",
        "resources": [],
        "cta": {"label": "", "url": ""},
    }


# ============================================================
# Public API
# ============================================================


#: Mapping cockpit-key → defaults-factory for the v3.57.0 platform sweep.
TENANT_V3_EXTENDED_DEFAULTS: dict[str, Any] = {
    "ai_study_buddy": _tenant_ai_study_buddy_defaults,
    "parent_teacher_thread": _tenant_parent_teacher_thread_defaults,
    "realtime_presence": _tenant_realtime_presence_defaults,
    "gradebook_trend": _tenant_gradebook_trend_defaults,
    "attendance_heatmap": _tenant_attendance_heatmap_defaults,
    "financial_timeline": _tenant_financial_timeline_defaults,
    "sibling_compare": _tenant_sibling_compare_defaults,
    "life_event_timeline": _tenant_life_event_timeline_defaults,
    "calendar_weather": _tenant_calendar_weather_defaults,
    "lesson_of_day": _tenant_lesson_of_day_defaults,
}


def build_tenant_v3_extended_cockpit() -> dict[str, Any]:
    """Return a fresh dict of every v3 extended cockpit section default.

    Mutation-safe — each call returns independently-constructed dicts.
    """
    return {key: factory() for key, factory in TENANT_V3_EXTENDED_DEFAULTS.items()}


__all__ = [
    "TENANT_V3_EXTENDED_DEFAULTS",
    "build_tenant_v3_extended_cockpit",
    "_tenant_ai_study_buddy_defaults",
    "_tenant_parent_teacher_thread_defaults",
    "_tenant_realtime_presence_defaults",
    "_tenant_gradebook_trend_defaults",
    "_tenant_attendance_heatmap_defaults",
    "_tenant_financial_timeline_defaults",
    "_tenant_sibling_compare_defaults",
    "_tenant_life_event_timeline_defaults",
    "_tenant_calendar_weather_defaults",
    "_tenant_lesson_of_day_defaults",
]
