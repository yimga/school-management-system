"""Scheduling Celery tasks — OR-Tools CP-SAT when installed (OSS), greedy fallback otherwise."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="academics.run_scheduling_solver", bind=True, ignore_result=False)
def run_scheduling_solver_task(
    self,
    school_id: int,
    *,
    use_ortools: bool = True,
    created_by_id: int | None = None,
) -> dict:
    from apps.schools.celery_tasks import _run_with_tenant_context

    def _run() -> dict:
        return _run_scheduling_solver_body(
            school_id, use_ortools=use_ortools, created_by_id=created_by_id
        )

    try:
        return _run_with_tenant_context(school_id=str(school_id), runnable=_run)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "scheduling.solver_tenant_context_failed school=%s err=%s",
            school_id,
            exc,
        )
        return _run()


def _run_scheduling_solver_body(
    school_id: int, *, use_ortools: bool = True, created_by_id: int | None = None
) -> dict:
    from django.contrib.auth import get_user_model

    from apps.academics.models import AcademicYear, Term
    from apps.academics.scheduling_solver import generate_timetable_with_solver
    from apps.schools.models import School

    User = get_user_model()
    try:
        school = School.objects.get(pk=school_id)
    except School.DoesNotExist:
        return {"ok": False, "error": "school_not_found"}

    year = (
        AcademicYear.objects.filter(school=school, is_active=True)
        .order_by("-start_date")
        .first()
    )
    if year is None:
        return {"ok": False, "error": "no_active_academic_year"}

    term = (
        Term.objects.filter(academic_year=year, school=school, is_active=True)
        .order_by("-start_date")
        .first()
    )
    if term is None:
        term = Term.objects.filter(academic_year=year, school=school).order_by("-start_date").first()
    if term is None:
        return {"ok": False, "error": "no_term"}

    created_by = None
    if created_by_id:
        created_by = User.objects.filter(
            pk=created_by_id
        ).first()  # tenant-isolation-allow: actor-attribution-lookup-of-one-global-auth-User-by-pk
    if created_by is None:
        created_by = User.objects.filter(is_staff=True).order_by(
            "pk"
        ).first()  # tenant-isolation-allow: system-actor-attribution-user-is-staff-not-tenant-scoped
    if created_by is None:
        return {"ok": False, "error": "no_staff_user"}

    from django.db import connection

    from apps.platform_runtime.workflow_telemetry import (
        TASK_TIMETABLE_SOLVER,
        update_and_broadcast_progress,
    )
    from apps.platform_runtime.workflow_tracker import ensure_workflow_run

    def _on_progress(processed, expected, message):
        update_and_broadcast_progress(
            school=school,
            task_type=TASK_TIMETABLE_SOLVER,
            processed=processed,
            expected=expected,
            log_message=message,
        )

    schema = str(getattr(connection, "schema_name", "") or "")
    try:
        with ensure_workflow_run(
            "academics-timetable-generate",
            steps=("load_constraints", "place_demands"),
            expected_duration_seconds=300,  # magic-number-allow: workflow-expected-duration-seconds
            school_id=str(getattr(school, "pk", "") or ""),
            tenant_schema=schema,
            payload={"task_type": TASK_TIMETABLE_SOLVER},
        ):
            schedule = generate_timetable_with_solver(
                academic_year=year,
                term=term,
                created_by=created_by,
                use_ortools=use_ortools,
                on_progress=_on_progress,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("scheduling.solver_failed school=%s err=%s", school_id, exc)
        return {"ok": False, "error": str(exc)[:200]}

    if schedule is None:
        return {"ok": False, "error": "solver_returned_none"}

    logger.info(
        "scheduling.solver_complete school=%s schedule=%s",
        school_id,
        getattr(schedule, "pk", None),
    )
    return {
        "ok": True,
        "school_id": school_id,
        "schedule_id": getattr(schedule, "pk", None),
        "schedule_name": getattr(schedule, "name", ""),
    }
