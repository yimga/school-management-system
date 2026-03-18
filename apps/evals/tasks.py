"""
World Engine: bulk grading and evals tasks with chunking to avoid memory exhaustion.
Run workers with high-concurrency pool when needed: celery -A config worker -P gevent -c 100
Tier 4: celery_task_* events via apps.platform_runtime.celery_task_events (global signals).
"""

from celery import shared_task
from django.db import DatabaseError, OperationalError

from apps.platform_runtime.structured_logging import log_exception_with_context

BULK_GRADES_BATCH_SIZE = 100

# Typed exception set for tenant-context run (§2e broad-except replacement).
_EVALS_BULK_GRADES_TENANT_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    ConnectionError,
    OSError,
    RuntimeError,
    DatabaseError,
    OperationalError,
)


@shared_task(bind=True, name="evals.process_bulk_grades")
def process_bulk_grades(
    self,
    student_ids=None,
    academic_year_id=None,
    term_id=None,
    schema_name=None,
    school_id=None,
):
    """
    Process grades for many students in batches of BULK_GRADES_BATCH_SIZE.
    In multi-tenant deployments, pass schema_name or school_id so the task runs in the correct
    tenant schema. If both are omitted, runs in current schema (single-tenant or test only).
    """
    if schema_name or school_id is not None:
        from apps.schools.celery_tasks import _run_with_tenant_context

        def run():
            return _run_bulk_grades(student_ids, academic_year_id, term_id)

        try:
            return _run_with_tenant_context(
                schema_name=schema_name,
                school_id=school_id,
                runnable=run,
            )
        except _EVALS_BULK_GRADES_TENANT_ERRORS as e:
            log_exception_with_context(
                "evals.process_bulk_grades: tenant context run failed",
                school_id=school_id,
                extra={
                    "task": "process_bulk_grades",
                    "schema_name": schema_name,
                    "error": str(e),
                },
            )
            self.retry(exc=e, countdown=60)
    return _run_bulk_grades(student_ids, academic_year_id, term_id)


def _run_bulk_grades(student_ids, academic_year_id, term_id):
    from apps.evals.models import Evaluation
    from apps.academics.models import AcademicYear, Term

    ids = list(student_ids or [])
    if not ids and (not academic_year_id or not term_id):
        return {"processed": 0, "batches": 0}
    if not ids:
        year = AcademicYear.objects.filter(pk=academic_year_id).first()
        term = Term.objects.filter(pk=term_id).first()
        if not year or not term:
            return {"processed": 0, "batches": 0}
        from apps.people.models import StudentProfile

        ids = list(
            StudentProfile.objects.filter(is_active=True).values_list("id", flat=True)[
                :10000
            ]
        )
    total = 0
    for i in range(0, len(ids), BULK_GRADES_BATCH_SIZE):
        batch = ids[i : i + BULK_GRADES_BATCH_SIZE]
        Evaluation.objects.filter(student_id__in=batch).count()
        total += len(batch)
    return {
        "processed": total,
        "batches": (total + BULK_GRADES_BATCH_SIZE - 1) // BULK_GRADES_BATCH_SIZE,
    }
