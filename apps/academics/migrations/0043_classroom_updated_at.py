from django.db import migrations, models
from django.utils import timezone


def _backfill_classroom_updated_at(apps, schema_editor):
    Classroom = apps.get_model("academics", "Classroom")
    now = timezone.now()
    Classroom.objects.filter(updated_at__isnull=True).update(updated_at=now)


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0042_materialize_extracted_runtime_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="classroom",
            name="updated_at",
            field=models.DateTimeField(null=True, blank=True, editable=False),
        ),
        migrations.RunPython(_backfill_classroom_updated_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="classroom",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
