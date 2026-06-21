"""
School activation onboarding: real checklist derived from tenant data (no synthetic completion).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def onboarding_import_quality_display(percent: int) -> dict[str, str]:
    """Map checklist completion to data-quality meter token + label."""
    pct = min(100, max(0, int(percent or 0)))
    if pct >= 100:
        return {"token": "ready", "label": str(_("Ready"))}
    if pct >= 80:
        return {"token": "partial", "label": str(_("Nearly complete"))}
    if pct > 0:
        return {"token": "needs-review", "label": str(_("Validate before apply"))}
    return {"token": "needs-review", "label": str(_("Not started"))}


def _reverse_tenant(name: str) -> str:
    try:
        return reverse(name, urlconf="config.tenant_urls")
    except NoReverseMatch:
        try:
            return reverse(name)
        except NoReverseMatch:
            return ""


def _load_manual_onboarding_step_keys(school) -> set[str]:
    if school is None:
        return set()
    try:
        from apps.platform_runtime.models import SchoolOnboardingProgress

        row = SchoolOnboardingProgress.objects.filter(school_id=school.id).first()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return set()
    if not row or not row.completed_steps:
        return set()
    return {str(x) for x in row.completed_steps if x}


def _compute_data_driven_onboarding_steps(
    school, user: Optional[Any] = None
) -> list[dict[str, Any]]:  # noqa: ARG001
    """
    Return checklist rows from live tenant data only: key, label, done, link, weight.
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

    # 5) Classes (classrooms) — CP list first (admin gravity)
    try:
        from apps.academics.models import Classroom

        has_classes = Classroom.objects.filter(school_id=school.id).exists()
        c_link = _reverse_tenant("accounts:backend_classroom_list")
        if not c_link:
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
        # Tenant-facing domains wizard (@login_required). NOT
        # siteconfig:console_domains_hub — that hub is @staff_member_required
        # (operator console) so a tenant admin clicking it gets bounced.
        ccc = _reverse_tenant("siteconfig:custom_domain_wizard")
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

    # 9) Data migration (CSV) — real audit trail when import/dry-run ran
    try:
        from apps.automation.models import MigrationRun

        has_migration_activity = MigrationRun.objects.filter(
            school_id=school.id
        ).exists()
        mig_link = _reverse_tenant("accounts:migration_wizard")
        add_row(
            "data_migration",
            "Data import (CSV migration) used or reviewed",
            has_migration_activity,
            mig_link,
        )
    except Exception as ex:  # noqa: BLE001
        logger.debug("onboarding data_migration: %s", ex)

    # 10) Guided configuration — setup studio progress or tenant runtime hub
    try:
        from apps.setup_studio.models import SetupProgress

        sp = SetupProgress.objects.filter(school_id=school.id).first()
        setup_done = bool(
            sp
            and (
                int(getattr(sp, "health_score", 0) or 0) >= 15
                or len(getattr(sp, "completed_keys", None) or []) > 0
            )
        )
        cfg_link = _reverse_tenant("siteconfig:tenant_runtime_configuration_hub")
        if not cfg_link:
            # Fallback must stay tenant-facing: console_domains_hub is
            # @staff_member_required, so it would bounce a tenant admin.
            cfg_link = _reverse_tenant("siteconfig:custom_domain_wizard")
        add_row(
            "guided_configuration",
            "Tenant settings & runtime (guided setup)",
            setup_done,
            cfg_link,
        )
    except Exception as ex:  # noqa: BLE001
        logger.debug("onboarding guided_configuration: %s", ex)

    # 11) Plan & entitlements (read-only billing summary)
    try:
        plan = getattr(school, "plan", None)
        has_plan = plan is not None
        plink = _reverse_tenant("siteconfig:billing_plan_readonly")
        add_row(
            "plan_entitlements",
            "Plan & entitlements reviewed",
            has_plan,
            plink,
        )
    except Exception as ex:  # noqa: BLE001
        logger.debug("onboarding plan_entitlements: %s", ex)

    return steps


def get_onboarding_steps(
    school, user: Optional[Any] = None
) -> list[dict[str, Any]]:
    """
    Checklist rows with data-driven *and* operator-marked completion merged.

    Each row is enriched with catalog metadata
    (label / description / audience / estimated_minutes / deep_link) from
    ``apps.siteconfig.onboarding_step_catalog`` when the row key matches
    a catalog entry.
    """
    base = _compute_data_driven_onboarding_steps(school, user=user)
    manual = _load_manual_onboarding_step_keys(school)

    catalog: dict[str, dict] = {}
    try:
        from apps.siteconfig.onboarding_step_catalog import ONBOARDING_STEPS
        catalog = ONBOARDING_STEPS
    except Exception:  # noqa: BLE001 - catalog is enrichment-only; never block onboarding
        catalog = {}

    out: list[dict[str, Any]] = []
    for row in base:
        r = dict(row)
        if r.get("key") in manual and not r.get("done"):
            r["done"] = True
            r["manually_completed"] = True
        cat_entry = catalog.get(r.get("key") or "")
        if cat_entry:
            for cat_key in ("label", "description", "audience", "estimated_minutes", "deep_link"):
                if cat_key in cat_entry and cat_key not in r:
                    r[cat_key] = cat_entry[cat_key]
        out.append(r)
    return out


def get_blueprint_recommended_onboarding_steps(
    blueprint_slug: Optional[str],
) -> list[dict[str, Any]]:
    """Return the catalog-recommended ordered step list for a blueprint slug.

    Use from wizard / setup-assistant views that want to *prompt* the
    operator with the canonical order — orthogonal to the data-driven
    completion check that ``get_onboarding_steps`` performs.
    """
    try:
        from apps.siteconfig.onboarding_step_catalog import steps_for_blueprint
    except Exception:  # noqa: BLE001
        return []
    return steps_for_blueprint(blueprint_slug)


# Backward compatibility / existing imports
get_school_onboarding_steps = get_onboarding_steps


def mark_school_onboarding_step_complete(school, step_key: str) -> dict[str, Any]:
    """
    Record an operator acknowledgment for a step key. Idempotent. Persists
    :class:`SchoolOnboardingProgress` and returns the same structure as
    :func:`get_school_onboarding_progress`.
    """
    from apps.platform_runtime.models import SchoolOnboardingProgress

    if school is None:
        raise ValueError("school required")
    valid = {r["key"] for r in _compute_data_driven_onboarding_steps(school, None)}
    sk = (step_key or "").strip()
    if sk not in valid:
        raise ValueError("unknown_onboarding_step")
    obj, _ = SchoolOnboardingProgress.objects.get_or_create(
        school_id=school.id,
        defaults={"completed_steps": [], "progress_percent": 0, "last_step": ""},
    )
    current = [str(x) for x in (obj.completed_steps or []) if x]
    if sk not in current:
        current.append(sk)
    obj.completed_steps = current
    obj.last_step = sk
    obj.save(update_fields=["completed_steps", "last_step", "updated_at"])
    return get_school_onboarding_progress(school, user=None)


def get_school_onboarding_progress(
    school, user: Optional[Any] = None
) -> dict[str, Any]:
    """
    Aggregated progress, next action, and display slice for dashboard card.
    """
    steps = get_onboarding_steps(school, user=user)
    if not steps:
        quality = onboarding_import_quality_display(0)
        return {
            "percent": 0,
            "completed": 0,
            "total": 0,
            "weight_done": 0,
            "weight_total": 0,
            "steps": [],
            "display_steps": [],
            "next_action": None,
            "persisted_last_step": "",
            "import_quality_token": quality["token"],
            "import_quality_label": quality["label"],
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
            # Tenant-facing only — never fall back to console_domains_hub (staff-only).
            "url": _reverse_tenant("siteconfig:onboarding")
            or _reverse_tenant("setup_studio:tenant_wizard_index"),
        }

    # Show EVERY step as a card (incomplete first), not a truncated slice — the
    # ring/count report the full total, so a cap left the surface saying e.g.
    # "8/9" while rendering only 5 cards. get_onboarding_steps returns a bounded,
    # curated milestone list and the cards use a responsive auto-fill grid, so the
    # full set simply wraps to more rows.
    ordered = [s for s in steps if not s.get("done")] + [s for s in steps if s.get("done")]
    display_steps = ordered

    pct = min(100, max(0, percent))
    quality = onboarding_import_quality_display(pct)
    result = {
        "percent": pct,
        "completed": completed,
        "total": total,
        "weight_done": weight_done,
        "weight_total": weight_total,
        "steps": steps,
        "display_steps": display_steps,
        "next_action": next_action,
        "persisted_last_step": "",
        "import_quality_token": quality["token"],
        "import_quality_label": quality["label"],
    }
    if school is not None:
        try:
            from apps.platform_runtime.models import SchoolOnboardingProgress

            rec = SchoolOnboardingProgress.objects.filter(school_id=school.id).first()
            if rec is not None:
                result["persisted_last_step"] = (rec.last_step or "").strip()
                pc = int(result["percent"])
                if int(rec.progress_percent or 0) != pc:
                    rec.progress_percent = pc
                    rec.save(update_fields=["progress_percent", "updated_at"])
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            pass
    return result
