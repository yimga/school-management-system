# Generated manually — student list FTS index column + backfill

from django.db import migrations, models


def _backfill_student_search_index(apps, schema_editor):
    StudentProfile = apps.get_model("people", "StudentProfile")
    batch: list[StudentProfile] = []
    for row in StudentProfile.objects.iterator(chunk_size=500):
        parts = [
            (row.first_name or "").strip(),
            (row.last_name or "").strip(),
            (row.student_code or "").strip(),
            (row.admission_number or "").strip(),
        ]
        row.search_index = " ".join(p.lower() for p in parts if p)
        batch.append(row)
        if len(batch) >= 500:
            StudentProfile.objects.bulk_update(batch, ["search_index"])
            batch = []
    if batch:
        StudentProfile.objects.bulk_update(batch, ["search_index"])


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0050_rename_people_stud_school__8f0a2d_idx_people_stud_school__dacb55_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="search_index",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Precomputed lowercase search text for backend list FTS.",
            ),
        ),
        migrations.RunPython(_backfill_student_search_index, migrations.RunPython.noop),
    ]
