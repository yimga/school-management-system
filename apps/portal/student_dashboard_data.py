"""Student role-home data bundle for the .rmc-dh 100X grammar.

Degrade-safe: every list defaults empty; panels hide when data is absent.
Reuses parent-dashboard per-student helpers in apps.portal.services.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.portal.student_results_visibility import (
    get_student_results_visibility_from_site,
    resolve_student_grade_dashboard_access,
    STUDENT_RESULTS_VISIBILITY_OFF,
    STUDENT_RESULTS_VISIBILITY_ENTERED,
)

try:
    from django.db import DatabaseError
except ImportError:  # pragma: no cover
    DatabaseError = Exception

_SOFT = (AttributeError, DatabaseError, TypeError, ValueError, KeyError, IndexError)


def _spark_heights(trend: list[dict], *, max_px: int = 22, min_px: int = 4) -> list[int]:
    values = [int(row.get("value") or 0) for row in (trend or [])]
    if not values:
        return []
    peak = max(values) or 1
    return [max(min_px, int(round(v / peak * max_px))) for v in values]


def _heat_levels(trend: list[dict]) -> list[dict]:
    cells = []
    for row in trend or []:
        v = int(row.get("value") or 0)
        if v >= 85:
            level = "l3"
        elif v >= 60:
            level = "l2"
        elif v > 0:
            level = "l1"
        else:
            level = ""
        cells.append({"label": row.get("label") or "", "level": level})
    return cells


def _student_due_items(profile, *, school, year, term) -> list[dict]:
    if profile is None or not getattr(profile, "classroom_id", None):
        return []
    try:
        from apps.academics.models_lms import LMSAssignment, LMSSubmission
    except _SOFT:
        return []

    now = timezone.now()
    week_end = now + timedelta(days=7)
    qs = LMSAssignment.objects.filter(
        classroom_id=profile.classroom_id,
        status=LMSAssignment.Status.PUBLISHED,
        due_at__isnull=False,
        due_at__gte=now - timedelta(days=1),
        due_at__lte=week_end,
    )
    if school is not None:
        qs = qs.filter(school=school)
    if term is not None:
        qs = qs.filter(term=term)
    assignments = list(qs.order_by("due_at")[:6])
    if not assignments:
        return []

    submitted = set(
        LMSSubmission.objects.filter(
            student=profile,
            assignment_id__in=[a.id for a in assignments],
            status__in=(
                LMSSubmission.Status.SUBMITTED,
                LMSSubmission.Status.LATE,
                LMSSubmission.Status.GRADED,
            ),
        ).values_list("assignment_id", flat=True)
    )
    items = []
    for assignment in assignments:
        if assignment.id in submitted:
            continue
        due_local = timezone.localtime(assignment.due_at)
        items.append(
            {
                "title": f"{assignment.subject.name} — {assignment.title}",
                "when": due_local,
                "cd": due_local.strftime("%a, %b %d"),
                "soon": (assignment.due_at - now).total_seconds() < 86400 * 2,
                "url": reverse("portal:portal_syllabus"),
            }
        )
    return items[:4]


def _student_ai_insight(*, grade_trend: list, subjects: list) -> dict | None:
    """Honest rules-based insight from grade trend — not an LLM call."""
    if len(grade_trend) >= 2:
        first = float(grade_trend[0].get("value") or 0)
        last = float(grade_trend[-1].get("value") or 0)
        if last > first + 1:
            top = subjects[0]["subject"] if subjects else _("your work")
            return {
                "title": _("Your recent scores are trending up"),
                "text": _(
                    "Keep the momentum — your latest published scores improved. "
                    "Open your syllabus to prepare for what's next."
                ),
                "acts": [
                    {"label": _("Open syllabus"), "href": reverse("portal:portal_syllabus")},
                    {"label": _("Messages"), "href": reverse("accounts:user_messages")},
                ],
            }
    if subjects:
        subj = subjects[0]
        return {
            "title": _("Strongest subject right now: %(subject)s") % {"subject": subj["subject"]},
            "text": _("Your published average is %(avg)s — keep building on that strength.")
            % {"avg": subj.get("average")},
            "acts": [
                {"label": _("Syllabus & resources"), "href": reverse("portal:portal_syllabus")},
            ],
        }
    return None


def build_student_home_extras(
    request,
    profile,
    *,
    unread: int,
    year,
    term,
) -> dict[str, Any]:
    school = getattr(request, "school", None)
    site = None
    try:
        from apps.siteconfig.config_service import get_effective_site_settings

        site = get_effective_site_settings(request=request)
    except _SOFT:
        pass

    attendance_pct = None
    grade_avg = None
    grade_trend: list = []
    timetable: list = []
    subjects: list = []
    badges: list = []
    attendance_trend: list = []
    due_items: list = []
    announcements: list = []
    can_view_results = False
    results_locked = False
    visibility_mode = get_student_results_visibility_from_site(site)
    attendance_cells: list = []
    spark_attendance: list = []
    spark_grades: list = []
    ai_insight = None
    classes_today = 0
    term_published = False
    grades_enabled = visibility_mode != STUDENT_RESULTS_VISIBILITY_OFF

    if profile is not None and getattr(profile, "classroom", None) and year and term:
        from apps.portal.services import (
            _attendance_snapshot,
            _attendance_trend,
            _grade_trend,
            _performance_overview,
            _subject_performance,
            _timetable_overview,
        )
        from apps.reports.services import is_term_published

        one = [profile]
        try:
            att = _attendance_snapshot(one, year, term) or {}
            attendance_pct = int(att.get("overall") or 0)
        except _SOFT:
            pass
        try:
            timetable = list(_timetable_overview(one, year, term) or [])
            classes_today = len(timetable)
        except _SOFT:
            timetable = []
        try:
            attendance_trend = list(_attendance_trend(one, year, term) or [])
            attendance_cells = _heat_levels(attendance_trend)
            spark_attendance = _spark_heights(attendance_trend)
        except _SOFT:
            attendance_trend = []
        try:
            due_items = _student_due_items(profile, school=school, year=year, term=term)
        except _SOFT:
            due_items = []

        if grades_enabled:
            try:
                perf = _performance_overview(one, year, term, school=school) or {}
                if perf.get("average") is not None:
                    grade_avg = round(float(perf["average"]), 1)
            except _SOFT:
                pass
            try:
                grade_trend = list(_grade_trend(one, year, term) or [])
                spark_grades = _spark_heights(grade_trend)
            except _SOFT:
                grade_trend = []
            try:
                subjects = list(_subject_performance(one, year, term) or [])
            except _SOFT:
                subjects = []
            try:
                term_published = is_term_published(
                    year.id, term.id, profile.classroom_id
                )
            except _SOFT:
                term_published = False

        try:
            from django.db.models import Q

            from apps.people.models import Badge

            badges = list(
                Badge.objects.filter(student=profile)
                .filter(Q(expiry_at__isnull=True) | Q(expiry_at__gt=timezone.now()))
                .select_related("badge_type")
                .order_by("-issued_at")[:6]
            )
        except _SOFT:
            badges = []

    has_grade_data = grade_avg is not None or bool(subjects) or bool(grade_trend)
    access = resolve_student_grade_dashboard_access(
        visibility_mode=visibility_mode,
        term_published=term_published,
        has_grade_data=has_grade_data,
    )
    can_view_results = bool(access.get("can_view_results"))
    results_locked = bool(access.get("results_locked"))
    visibility_mode = str(access.get("visibility_mode") or visibility_mode)

    if can_view_results:
        ai_insight = _student_ai_insight(grade_trend=grade_trend, subjects=subjects)

    if site is not None:
        try:
            from apps.accounts.models import User
            from apps.siteconfig.models_support import filter_portal_items

            role = User.Role.STUDENT
            for item in filter_portal_items(site.portal_announcements, role)[:4]:
                announcements.append(
                    {
                        "title": item.get("title") or item.get("label") or "",
                        "meta": item.get("meta") or item.get("description") or "",
                    }
                )
        except _SOFT:
            pass

    term_label = getattr(term, "label", None) or getattr(term, "name", "")
    year_label = getattr(year, "name", "") if year else ""
    eyebrow = _("Student home")
    if year_label and term_label:
        eyebrow = _("Student home · %(year)s · %(term)s") % {
            "year": year_label,
            "term": term_label,
        }

    due_count = len(due_items)
    sub_parts = []
    if classes_today:
        sub_parts.append(
            _("%(n)s class(es) today") % {"n": classes_today}
            if classes_today != 1
            else _("1 class today")
        )
    if due_count:
        sub_parts.append(
            _("%(n)s task(s) due this week") % {"n": due_count}
            if due_count != 1
            else _("1 task due this week")
        )
    if attendance_pct is not None and attendance_pct >= 80:
        sub_parts.append(_("attendance strong"))
    hero_sub = " · ".join(sub_parts) if sub_parts else _("Your priorities for today.")

    metrics = []
    if attendance_pct is not None:
        metrics.append(
            {
                "label": _("Attendance"),
                "value": f"{attendance_pct}%",
                "meta": _("on track") if attendance_pct >= 90 else _("watch"),
                "status": "ok" if attendance_pct >= 90 else "warn",
                "dir": "up" if attendance_pct >= 90 else "down",
                "icon": "bi-calendar-check",
                "spark": spark_attendance,
            }
        )
    if can_view_results and grade_avg is not None:
        metrics.append(
            {
                "label": _("Average"),
                "value": str(grade_avg),
                "meta": _("live")
                if visibility_mode == STUDENT_RESULTS_VISIBILITY_ENTERED
                else _("published"),
                "status": "ok",
                "dir": "up",
                "icon": "bi-mortarboard",
                "spark": spark_grades,
            }
        )
    if due_count:
        metrics.append(
            {
                "label": _("Due this week"),
                "value": due_count,
                "meta": _("tasks"),
                "status": "warn",
                "dir": "down",
                "icon": "bi-journal-text",
            }
        )
    metrics.append(
        {
            "label": _("Unread"),
            "value": unread,
            "meta": _("from school"),
            "status": "warn" if unread else "ok",
            "dir": "flat",
            "icon": "bi-envelope",
            "href": reverse("accounts:user_messages"),
        }
    )

    subject_rows = []
    if can_view_results and subjects:
        for row in subjects:
            avg = float(row.get("average") or 0)
            subject_rows.append(
                {
                    "name": row.get("subject") or "",
                    "pct": min(100, int(round(avg * 5))),
                    "label": str(row.get("average")),
                }
            )

    grade_trend_out = grade_trend if can_view_results else []

    return {
        "student_attendance_pct": attendance_pct,
        "student_grade_avg": grade_avg if can_view_results or results_locked else None,
        "student_grade_trend": grade_trend_out,
        "student_timetable": timetable,
        "student_subjects": subjects if can_view_results else [],
        "student_subject_rows": subject_rows,
        "student_badges": badges,
        "student_due_items": due_items,
        "student_announcements": announcements,
        "student_attendance_cells": attendance_cells,
        "student_can_view_results": can_view_results,
        "student_results_locked": results_locked,
        "student_results_visibility_mode": visibility_mode,
        "student_ai_insight": ai_insight,
        "student_hero_eyebrow": eyebrow,
        "student_hero_sub": hero_sub,
        "student_metrics": metrics,
        "student_due_count": due_count,
    }
