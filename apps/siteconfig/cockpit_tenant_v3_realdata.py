"""Tenant v3 extended cockpit sections — DB-backed hydration (batch 1612/1615)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User

# "Online" window for the realtime-presence count (minutes since last_login).
_PRESENCE_WINDOW_MINUTES = 15
# Attendance.Status values that map 1:1 onto the heatmap cell tones.
_HEATMAP_STATUS_TONES = frozenset({"present", "absent", "late", "excused"})


def _hydrate_financial_timeline(
    section: dict[str, Any], widget_data: dict[str, dict]
) -> dict[str, Any]:
    fin = widget_data.get("finance") or {}
    balance = fin.get("balance")
    if balance is None:
        return section
    out = dict(section)
    out["enabled"] = True
    out["balance_display"] = str(balance)
    overdue = int(fin.get("overdue") or 0)
    out["balance_tone"] = "warn" if overdue else "ok"
    events = []
    if overdue:
        events.append(
            {
                "iso": "",
                "label": str(_("Overdue fees")),
                "amount_display": str(balance),
                "tone": "fee",
                "icon": "!",
            }
        )
    out["events"] = events
    out["a8_wire_pending"] = False
    return out


def _hydrate_ai_study_buddy(request: HttpRequest, section: dict[str, Any]) -> dict[str, Any]:
    user = getattr(request, "user", None)
    if user is None or str(getattr(user, "role", "") or "").upper() != User.Role.STUDENT:
        return section
    try:
        url = reverse("portal:ai_stream")
    except Exception:
        try:
            url = reverse("portal:student_portal_grades")
        except Exception:
            url = ""
    if not url:
        return section
    out = dict(section)
    out["enabled"] = True
    out["wire_pending"] = False
    out["a8_wire_pending"] = False
    out["suggestions"] = [
        {
            "icon": "✦",
            "label": str(_("Open study assist")),
            "url": url,
        }
    ]
    return out


def _hydrate_gradebook_trend(
    request: HttpRequest, section: dict[str, Any]
) -> dict[str, Any]:
    user = getattr(request, "user", None)
    if user is None or str(getattr(user, "role", "") or "").upper() != User.Role.STUDENT:
        return section
    try:
        from apps.evals.models import Evaluation
        from apps.academics.services import get_active_year_and_term
        from apps.people.models import StudentProfile

        year, term = get_active_year_and_term(school=getattr(request, "school", None))
        if not year or not term:
            return section
        school = getattr(request, "school", None)
        if school is None:
            return section
        profile = (
            StudentProfile.objects.filter(user=user, is_active=True, school=school)
            .select_related("classroom")
            .first()
        )
        if profile is None:
            return section
        qs = (
            Evaluation.objects.filter(
                student=profile,
                academic_year=year,
                term=term,
                school=school,
            )
            .select_related("subject_assignment__subject")
        )
        subjects: list[dict[str, Any]] = []
        seen: set[str] = set()
        for ev in qs[:12]:
            sa = getattr(ev, "subject_assignment", None)
            subject = getattr(sa, "subject", None) if sa else None
            name = getattr(subject, "name", None) if subject else None
            if not name or name in seen:
                continue
            seen.add(name)
            avg = getattr(ev, "average", None) or getattr(ev, "total", None)
            if avg is None:
                continue
            subjects.append(
                {
                    "subject": str(name),
                    "current_value": str(avg),
                    "delta_text": "",
                    "delta_tone": "",
                    "spark_points": "",
                }
            )
        if not subjects:
            return section
        out = dict(section)
        out["enabled"] = True
        out["subjects"] = subjects[:6]
        out["a8_wire_pending"] = False
        return out
    except Exception:
        return section


def _build_heatmap_cells(rows, today, month_start, next_month) -> list[dict[str, Any]]:
    """Pure: build the month-grid cells from aggregated ``(date, status, n)`` rows.

    Each calendar day gets the DOMINANT attendance status for that day (highest
    count) as its tone; days with no attendance fall back to "weekend" (Sat/Sun)
    or "" (a plain weekday with no records). No PII — cells are per-day, never
    per-student. ``rows`` items are dicts with ``date`` / ``status`` / ``n`` keys.
    """
    dominant: dict[Any, tuple[str, int]] = {}
    for r in rows:
        d = r.get("date")
        if d is None:
            continue
        status = str(r.get("status") or "")
        n = int(r.get("n") or 0)
        cur = dominant.get(d)
        if cur is None or n > cur[1]:
            dominant[d] = (status, n)

    cells: list[dict[str, Any]] = []
    day = month_start
    while day < next_month:
        tone = ""
        if day in dominant:
            tone = dominant[day][0]
        elif day.weekday() >= 5:
            tone = "weekend"
        cells.append(
            {
                "day": day.day,
                "tone": tone,
                "tooltip": day.strftime("%a %d %b"),
                "is_today": day == today,
            }
        )
        day += timedelta(days=1)
    return cells


def _is_tenant_admin(user) -> bool:
    role = str(getattr(user, "role", "") or "").upper()
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or role == User.Role.ADMIN
    )


def _hydrate_attendance_heatmap(
    request: HttpRequest, section: dict[str, Any]
) -> dict[str, Any]:
    """Auto-derive the current-month attendance heatmap (admin cockpit, aggregate).

    School-wide daily aggregate — strictly more PII-safe than a per-student snapshot.
    Operator-published cells win (we never overwrite them); a school with no
    attendance this month is left disabled so the grid never shows empty.
    """
    user = getattr(request, "user", None)
    if user is None or not _is_tenant_admin(user):
        return section
    if section.get("cells"):  # operator already published → override wins
        return section
    school = getattr(request, "school", None)
    if school is None:
        return section
    try:
        from django.db.models import Count

        from apps.academics.models import Attendance

        today = timezone.localdate()
        month_start = today.replace(day=1)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)
        rows = list(
            # tenant-isolation-allow: school-scoped-aggregate-admin-cockpit-heatmap
            Attendance.objects.filter(
                school=school, date__gte=month_start, date__lt=next_month
            )
            .values("date", "status")
            .annotate(n=Count("id"))
        )
        cells = _build_heatmap_cells(rows, today, month_start, next_month)
        if not any(c["tone"] in _HEATMAP_STATUS_TONES for c in cells):
            return section  # no real attendance this month → stay disabled
        out = dict(section)
        out["enabled"] = True
        out["cells"] = cells
        out["month_label"] = today.strftime("%B %Y")
        out["legend"] = [
            {"tone": "present", "label": str(_("Present"))},
            {"tone": "absent", "label": str(_("Absent"))},
            {"tone": "late", "label": str(_("Late"))},
            {"tone": "excused", "label": str(_("Excused"))},
        ]
        out["a8_wire_pending"] = False
        return out
    except Exception:
        return section


def _hydrate_realtime_presence(
    request: HttpRequest, section: dict[str, Any]
) -> dict[str, Any]:
    """Auto-derive a COUNT-ONLY presence signal (students active in the window).

    Privacy: emits ``online_count`` / ``total_count`` only — never names or initials
    (``presence`` stays empty). "Online" = logged in within the window, the same
    semantic as the operator-presence panel. Operator-published presence wins.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return section
    if section.get("presence"):  # operator already published dots → override wins
        return section
    school = getattr(request, "school", None)
    if school is None:
        return section
    try:
        from apps.people.models import StudentProfile

        cutoff = timezone.now() - timedelta(minutes=_PRESENCE_WINDOW_MINUTES)
        # tenant-isolation-allow: school-scoped-student-presence-count-only
        base = StudentProfile.objects.filter(school=school, is_active=True)
        total = base.count()
        if total <= 0:
            return section
        online = base.filter(user__last_login__gte=cutoff).count()
        out = dict(section)
        out["enabled"] = True
        out["online_count"] = int(online)
        out["total_count"] = int(total)
        out["presence"] = []  # count-only by design
        out["a8_wire_pending"] = False
        return out
    except Exception:
        return section


def hydrate_tenant_v3_extended_realdata(
    request: HttpRequest, tenant_cockpit: dict[str, Any]
) -> dict[str, Any]:
    """Overlay live metrics on v3 extended sections when data exists."""
    from apps.portal.tenant_cockpit_realdata import _role_widget_bundle

    widget_data = _role_widget_bundle(request)

    if widget_data:
        ft = tenant_cockpit.get("financial_timeline")
        if isinstance(ft, dict):
            tenant_cockpit["financial_timeline"] = _hydrate_financial_timeline(
                ft, widget_data
            )

    gb = tenant_cockpit.get("gradebook_trend")
    if isinstance(gb, dict):
        tenant_cockpit["gradebook_trend"] = _hydrate_gradebook_trend(request, gb)

    ai = tenant_cockpit.get("ai_study_buddy")
    if isinstance(ai, dict):
        tenant_cockpit["ai_study_buddy"] = _hydrate_ai_study_buddy(request, ai)

    ah = tenant_cockpit.get("attendance_heatmap")
    if isinstance(ah, dict):
        tenant_cockpit["attendance_heatmap"] = _hydrate_attendance_heatmap(request, ah)

    rp = tenant_cockpit.get("realtime_presence")
    if isinstance(rp, dict):
        tenant_cockpit["realtime_presence"] = _hydrate_realtime_presence(request, rp)

    return tenant_cockpit


__all__ = ["hydrate_tenant_v3_extended_realdata"]
