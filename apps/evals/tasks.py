"""
World Engine: bulk grading and evals tasks with chunking to avoid memory exhaustion.
Run workers with high-concurrency pool when needed: celery -A config worker -P gevent -c 100
"""
from celery import shared_task

BULK_GRADES_BATCH_SIZE = 100


@shared_task(bind=True, name="evals.process_bulk_grades")
def process_bulk_grades(self, student_ids=None, academic_year_id=None, term_id=None, schema_name=None):
    """
    Process grades for many students in batches of BULK_GRADES_BATCH_SIZE.
    Pass schema_name when using django-tenants so the task runs in the correct tenant schema.
    """
    from django.db import connection
    if schema_name:
        try:
            from django_tenants.utils import schema_context
            with schema_context(schema_name):
                return _run_bulk_grades(student_ids, academic_year_id, term_id)
        except Exception as e:
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
        ids = list(StudentProfile.objects.filter(is_active=True).values_list("id", flat=True)[:10000])
    total = 0
    for i in range(0, len(ids), BULK_GRADES_BATCH_SIZE):
        batch = ids[i : i + BULK_GRADES_BATCH_SIZE]
        # Placeholder: actual grade computation would go here (e.g. recalc averages, publish)
        Evaluation.objects.filter(student_id__in=batch).count()  # touch the table
        total += len(batch)
    return {"processed": total, "batches": (total + BULK_GRADES_BATCH_SIZE - 1) // BULK_GRADES_BATCH_SIZE}
