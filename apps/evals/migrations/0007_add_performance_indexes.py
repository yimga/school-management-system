# Generated migration for Phase 1.1: Performance optimization indexes

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("evals", "0006_add_field_validators"),
    ]

    operations = [
        # Composite index on Evaluation for dashboard queries
        # Most common query: Evaluation.objects.filter(student__in=students, academic_year=year, term=term)
        migrations.AddIndex(
            model_name="evaluation",
            index=models.Index(
                fields=["student", "academic_year", "term"],
                name="evals_eval_student_year_term_idx",
            ),
        ),
        # Index for subject assignment lookups by teacher
        # Query pattern: SubjectAssignment.objects.filter(teacher=teacher, academic_year=year)
        migrations.AddIndex(
            model_name="evaluation",
            index=models.Index(
                fields=["subject_assignment", "student", "academic_year"],
                name="evals_eval_subject_student_year_idx",
            ),
        ),
    ]
