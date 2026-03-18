from django.db import migrations, models
from django.utils import timezone


def _backfill_updated_at(apps, schema_editor):
    TP = apps.get_model("people", "TeacherProfile")
    now = timezone.now()
    TP.objects.filter(updated_at__isnull=True).update(updated_at=now)


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0039_tenant_upload_to_profiles_passport"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacherprofile",
            name="updated_at",
            field=models.DateTimeField(null=True, blank=True, editable=False),
        ),
        migrations.RunPython(_backfill_updated_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="teacherprofile",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
