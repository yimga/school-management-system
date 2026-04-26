"""
School activation onboarding: real checklist derived from tenant data (no synthetic completion).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)


def _reverse_tenant(name: str) -> str:
    try:
        return reverse(name, urlconf="config.tenant_urls")
    except NoReverseMatch:
        try:
            return reverse(name)
        except NoReverseMatch:
            return ""


def get_school_onboarding_steps(
    school, user: Optional[Any] = None
) -> list[dict[str, Any]]:  # noqa: ARG001
    """
    Return checklist rows: key, label, done, link (action URL when not done, else empty).
    """
    del user  # reserved for future permission-scoped links
    if school is None:
        return []

    steps: list[dict[str, Any]] = []

    def add_row(
        key: str, label: str, done: bool, link: str, *, weight: int = 1
    ) -> None:
        steps.append(
            {
                "key": key,
                "label": label,
                "done": bool(done),
                "link": link or "",
                "weight": int(weight),
            }
        )

    # 1) Academic years
    try:
        from apps.academics.models import AcademicYear

        has_years = AcademicYear.objects.filter(school_id=school.id).exists()
        y_link = _reverse_tenant("siteconfig:academic_years_setup_evidence")
        if not y_link:
            y_link = _reverse_tenant("admin:academics_academicyear_changelist")
        add_row("academic_year", "Academic year configured", has_years, y_link)
    except Exception as ex:  # noqa: BLE001
        logger.debug("onboarding academic_year: %s", ex)

    # 2) Departments
    try:
        from apps.academics.models import Department

        has_dept = Department.objects.filter(school_id=school.id).exists()
        d_link = _reverse_tenant("siteconfig:departments_setup_evidence")
        add_row("departments", "Departments configured", has_dept, d_link)
    except Exception as ex:  # noqa: BLE001
        logger.debug("onboarding departments: %s", ex)

    # 3) Students
    try:
        from apps.people.models import StudentProfile

        has_students = StudentProfile.objects.filter(
            school_id=school.id, is_active=True
        ).exists()
        s_link = _reverse_tenant("accounts:backend_student_list")
        add_row("students", "Students on record", has_students, s_link)
    except Exception as ex:  # noqa: BLE001
        logger.debug("onboarding students: %s", ex)

    # 4) Teachers / staff
    try:
        from apps.people.models import TeacherProfile

        has_teachers = TeacherProfile.objects.filter(school_id=school.id).exists()
        t_link = _reverse_tenant("accounts:backend_teacher_list")
        add_row("teachers", "Teachers or staff on record", has_teachers, t_link)
    except Exception as ex:  # noqa: BLE001
        logger.debug("onboarding teachers: %s", ex)

    # 5) Classes (classrooms)
    try:
        from apps.academics.models import Classroom

        has_classes = Classroom.objects.filter(school_id=school.id).exists()
        c_link = _reverse_tenant("admin:academics_classroom_changelist")
        add_row("classes", "Classes (classrooms) set up", has_classes, c_link)
    except Exception as ex:  # noqa: BLE001
        logger.debug("onboarding classes: %s", ex)

    # 6) Reports: schedules or at least report templates area reviewed
    try:
        from apps.reports.models import TenantReportSchedule

        has_sched = TenantReportSchedule.objects.filter(school_id=school.id).exists()
        r_link = _reverse_tenant("siteconfig:tenant_report_schedules_evidence")
        if not has_sched:
            r_link = r_link or _reverse_tenant(
                "siteconfig:report_templates_catalog_evidence"
            )
        add_row("reports", "Report schedules or catalog in use", has_sched, r_link)
    except Exception as ex:  # noqa: BLE001
        logger.debug("onboarding reports: %s", ex)

    # 7) Command & control / domains
    try:
        from apps.schools.models import SchoolDomain

        has_domain = SchoolDomain.objects.filter(school_id=school.id).exists()
        ccc = _reverse_tenant("siteconfig:console_domains_hub")
        add_row("ccc", "Domains / email routing (CCC)", has_domain, ccc)
    except Exception as ex:  # noqa: BLE001
        logger.debug("onboarding ccc: %s", ex)

    # 8) Marketplace / packages
    try:
        from apps.packages.models import InstalledPackage

        has_pkg = InstalledPackage.objects.filter(
            school_id=school.id, is_active=True
        ).exists()
        m_link = _reverse_tenant("tenant_app_catalog")
        add_row("marketplace", "App catalog (install or review)", has_pkg, m_link)
    except Exception as ex:  # noqa: BLE001
        logger.debug("onboarding marketplace: %s", ex)

    return steps


def get_school_onboarding_progress(
    school, user: Optional[Any] = None
) -> dict[str, Any]:
    """
    Aggregated progress, next action, and display slice for dashboard card.
    """
    steps = get_school_onboarding_steps(school, user=user)
    if not steps:
        return {
            "percent": 0,
            "completed": 0,
            "total": 0,
            "weight_done": 0,
            "weight_total": 0,
            "steps": [],
            "display_steps": [],
            "next_action": None,
        }

    weight_total = sum(int(s.get("weight") or 1) for s in steps)
    weight_done = sum(
        int(s.get("weight") or 1) for s in steps if s.get("done")
    )
    total = len(steps)
    completed = sum(1 for s in steps if s.get("done"))
    percent = int(round(100 * weight_done / weight_total)) if weight_total else 0

    next_action = None
    for s in steps:
        if not s.get("done") and (s.get("link") or "").strip():
            next_action = {"label": s.get("label", ""), "url": s["link"]}
            break
    if next_action is None and steps:
        next_action = {
            "label": "Open full activation checklist",
            "url": _reverse_tenant("siteconfig:onboarding")
            or _reverse_tenant("siteconfig:console_domains_hub"),
        }

    # 3–5 items for card: prefer incomplete first
    ordered = [s for s in steps if not s.get("done")] + [s for s in steps if s.get("done")]
    display_steps = ordered[:5]

    return {
        "percent": min(100, max(0, percent)),
        "completed": completed,
        "total": total,
        "weight_done": weight_done,
        "weight_total": weight_total,
        "steps": steps,
        "display_steps": display_steps,
        "next_action": next_action,
    }
