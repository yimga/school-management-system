"""Cockpit tenant v3 100x preview data — v3.57.3 (2026-05-21).

Companion to ``cockpit_manager_200x_preview_data.py`` — pre-populated demo
payload that mirrors the tenant v3 100x design preview at
``docs/generated/preview_app_shell_tenant_portal_v3.html`` AND covers the
10 NEW tenant v3 extended sections shipped in v3.57.0
(``cockpit_tenant_v3_extended.py``: ai_study_buddy / parent_teacher_thread
/ realtime_presence / gradebook_trend / attendance_heatmap /
financial_timeline / sibling_compare / life_event_timeline /
calendar_weather / lesson_of_day).

When ``settings.COCKPIT_100X_RENDER_PREVIEW_DEMO`` is True (default: True
so tenant pages render the v3 100x experience out of the box), the
orchestrator overlays this payload on top of
``build_tenant_v3_extended_cockpit()`` so every section's ``enabled`` flag
becomes True AND every list is populated.

PII / PLACEHOLDER SAFETY
------------------------
Every string here is generic placeholder copy. Names like "Mr. Adekunle"
and "Ms. Chioma" are illustrative — operators see the demo content,
overlay their real values via the cockpit admin UI (v3.57.1), and the
``_deep_merge`` in ``cockpit_context.py`` honors per-field overrides.

Sibling-compare honors its separate ``opt_in`` privacy gate inside the
section payload — the demo sets ``opt_in=False`` so even with
``enabled=True`` no sibling data renders until a parent opts in.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _


# ============================================================
# 1. AI study buddy
# ============================================================

def _ai_study_buddy_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "label": _("Study buddy"),
        "greeting": _("Ask anything about today's lessons."),
        "suggestions": [
            {"icon": "✦", "label": _("Explain today's math lesson"), "url": ""},
            {"icon": "✦", "label": _("Quiz me on chapter 3"), "url": ""},
            {"icon": "✦", "label": _("Suggest a study plan"), "url": ""},
        ],
        "wire_pending": True,
        "a8_wire_pending": True,
    }


# ============================================================
# 2. Parent-teacher inline thread
# ============================================================

def _parent_teacher_thread_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "title": _("Teacher thread"),
        "teacher_name": "Mr. Adekunle",
        "messages": [
            {
                "author_initials": "MA",
                "author_label": "Mr. Adekunle",
                "body": _("Aleksandra had a great week — top score on the quiz."),
                "sent_iso": "2026-05-19T14:32:00Z",
                "mine": False,
            },
            {
                "author_initials": "PA",
                "author_label": _("You"),
                "body": _("That's wonderful, thank you for letting us know!"),
                "sent_iso": "2026-05-19T16:08:00Z",
                "mine": True,
            },
            {
                "author_initials": "MA",
                "author_label": "Mr. Adekunle",
                "body": _("She can prepare for the science project next week — I'll send materials Friday."),
                "sent_iso": "2026-05-20T09:14:00Z",
                "mine": False,
            },
        ],
        "reply": {
            "url": "",
            "placeholder": _("Reply to teacher…"),
            "cta": _("Send"),
        },
    }


# ============================================================
# 3. Realtime presence dots
# ============================================================

def _realtime_presence_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "title": _("Classmates online"),
        "online_count": 8,
        "total_count": 24,
        "presence": [
            {"initials": "AB", "online": True, "tone": ""},
            {"initials": "CD", "online": True, "tone": "focus"},
            {"initials": "EF", "online": True, "tone": ""},
            {"initials": "GH", "online": False, "tone": ""},
            {"initials": "IJ", "online": True, "tone": ""},
            {"initials": "KL", "online": True, "tone": ""},
            {"initials": "MN", "online": False, "tone": ""},
            {"initials": "OP", "online": True, "tone": "focus"},
            {"initials": "QR", "online": True, "tone": ""},
            {"initials": "ST", "online": True, "tone": ""},
        ],
        "a8_wire_pending": True,
    }


# ============================================================
# 4. Gradebook trend sparkline
# ============================================================

def _gradebook_trend_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "title": _("Gradebook trend"),
        "subtitle": _("Last 6 assessments"),
        "subjects": [
            {"label": _("Math"), "current": "92%", "trend": "up", "points": [76, 82, 80, 85, 88, 92]},
            {"label": _("English"), "current": "87%", "trend": "flat", "points": [84, 86, 85, 88, 86, 87]},
            {"label": _("Science"), "current": "78%", "trend": "down", "points": [86, 84, 82, 80, 79, 78]},
        ],
    }


# ============================================================
# 5. Attendance heatmap
# ============================================================

def _attendance_heatmap_demo() -> dict[str, Any]:
    # 30 days, mostly present, a few sick days.
    pattern = ["present"] * 22 + ["present"] * 3 + ["absent"] * 2 + ["tardy"] * 3
    days = [
        {"day": i + 1, "status": pattern[i]}
        for i in range(30)
    ]
    return {
        "enabled": True,
        "title": _("Attendance · this term"),
        "subtitle": _("30-day rolling"),
        "stats": {
            "present_pct": "93%",
            "absent_count": 2,
            "tardy_count": 3,
        },
        "days": days,
    }


# ============================================================
# 6. Financial timeline
# ============================================================

def _financial_timeline_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "title": _("Financial timeline"),
        "subtitle": _("Current term"),
        "balance_display": "$2,450.00",
        "balance_status": "current",
        "events": [
            {"date_iso": "2026-04-15", "label": _("Term fees invoice"), "amount_display": "-$3,200.00", "kind": "invoice"},
            {"date_iso": "2026-04-22", "label": _("Payment received"), "amount_display": "+$3,200.00", "kind": "payment"},
            {"date_iso": "2026-05-01", "label": _("Lunch program"), "amount_display": "-$180.00", "kind": "invoice"},
            {"date_iso": "2026-05-08", "label": _("Field trip fee"), "amount_display": "-$120.00", "kind": "invoice"},
            {"date_iso": "2026-05-12", "label": _("Auto-pay credit"), "amount_display": "+$500.00", "kind": "payment"},
        ],
    }


# ============================================================
# 7. Sibling compare (opt-in gated)
# ============================================================

def _sibling_compare_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        # Opt-in stays FALSE in the demo — sibling data NEVER renders without
        # the parent's explicit consent. Operator must flip opt_in via the
        # cockpit admin UI per parent.
        "opt_in": False,
        "title": _("Sibling compare"),
        "consent_text": _("Show this card only after parents have opted in via account settings."),
        "siblings": [],
    }


# ============================================================
# 8. Life event timeline
# ============================================================

def _life_event_timeline_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "title": _("Life events"),
        "subtitle": _("Year so far"),
        "events": [
            {"date_iso": "2026-01-15", "label": _("First day of term"), "kind": "milestone"},
            {"date_iso": "2026-02-14", "label": _("Birthday · 14 years"), "kind": "birthday"},
            {"date_iso": "2026-03-22", "label": _("Honor roll"), "kind": "achievement"},
            {"date_iso": "2026-04-12", "label": _("Science fair · 2nd place"), "kind": "achievement"},
            {"date_iso": "2026-05-08", "label": _("Field trip · Lagos Museum"), "kind": "milestone"},
        ],
    }


# ============================================================
# 9. Calendar + weather overlay
# ============================================================

def _calendar_weather_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "title": _("This week"),
        "subtitle": _("Calendar · weather"),
        "days": [
            {"day_label": _("Mon"), "date": 19, "event": _("Math quiz"), "weather": "☀ 28°"},
            {"day_label": _("Tue"), "date": 20, "event": "", "weather": "☀ 29°"},
            {"day_label": _("Wed"), "date": 21, "event": _("Science fair"), "weather": "⛅ 26°"},
            {"day_label": _("Thu"), "date": 22, "event": _("Parent conference"), "weather": "🌧 24°"},
            {"day_label": _("Fri"), "date": 23, "event": _("Field day"), "weather": "☀ 27°"},
        ],
    }


# ============================================================
# 10. Lesson of the day
# ============================================================

def _lesson_of_day_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "title": _("Today's lesson"),
        "subject": _("Mathematics · Period 2"),
        "topic": _("Introduction to Algebra"),
        "summary": _("Variables and expressions — how letters can stand for numbers in math."),
        "teacher_name": "Mr. Adekunle",
        "resources": [
            {"label": _("Worksheet PDF"), "url": ""},
            {"label": _("Practice problems"), "url": ""},
        ],
    }


# ============================================================
# Aggregator
# ============================================================

def tenant_v3_extended_demo_payload() -> dict[str, Any]:
    """Return the full v3 100x tenant demo payload — all 10 sections populated.

    Consumed by ``cockpit_context.py`` when
    ``settings.COCKPIT_100X_RENDER_PREVIEW_DEMO`` is True. Operators flip
    individual sections off via the v3.57.1 admin toggles; ``_deep_merge``
    overlays their cockpit_payload values on top of this payload.
    """
    return {
        "ai_study_buddy": _ai_study_buddy_demo(),
        "parent_teacher_thread": _parent_teacher_thread_demo(),
        "realtime_presence": _realtime_presence_demo(),
        "gradebook_trend": _gradebook_trend_demo(),
        "attendance_heatmap": _attendance_heatmap_demo(),
        "financial_timeline": _financial_timeline_demo(),
        "sibling_compare": _sibling_compare_demo(),
        "life_event_timeline": _life_event_timeline_demo(),
        "calendar_weather": _calendar_weather_demo(),
        "lesson_of_day": _lesson_of_day_demo(),
    }


__all__ = ["tenant_v3_extended_demo_payload"]
