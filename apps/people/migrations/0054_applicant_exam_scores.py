"""v4.00.34 — Applicant exam-score capture columns.

Adds three pure-additive columns to people.Applicant:
  * exam_scores (JSON)
  * exam_schema_code (varchar 40)
  * exam_marker (varchar 80)

Plus a composite (school, exam_schema_code) index so we can grep applicants
by schema lineage when the country mix grows.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0053_ensure_teacherprofile_updated_at_column"),
    ]

    operations = [
        migrations.AddField(
            model_name="applicant",
            name="exam_scores",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Per-subject scores keyed by schema subject code, "
                    "e.g. {'english': 'A1', 'math': 'B2'}."
                ),
            ),
        ),
        migrations.AddField(
            model_name="applicant",
            name="exam_schema_code",
            field=models.CharField(
                blank=True,
                max_length=40,
                help_text="Slug of the apps.siteconfig._admissions_intake_schemas entry used.",
            ),
        ),
        migrations.AddField(
            model_name="applicant",
            name="exam_marker",
            field=models.CharField(
                blank=True,
                max_length=80,
                help_text="Display label for the exam (WASSCE / KCSE / Thanaweya / Baccalauréat …).",
            ),
        ),
        migrations.AddIndex(
            model_name="applicant",
            index=models.Index(
                fields=["school", "exam_schema_code"],
                name="people_appl_school__269f5b_idx",
            ),
        ),
    ]
