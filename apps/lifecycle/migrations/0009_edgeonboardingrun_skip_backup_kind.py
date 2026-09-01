# Add EdgeOnboardingRun.kind = skip_backup (operator skip of the verified-backup
# go-dark gate). Choices-only; no schema change besides the documented values.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lifecycle", "0008_align_edgeonboardingrun_index_names"),
    ]

    operations = [
        migrations.AlterField(
            model_name="edgeonboardingrun",
            name="kind",
            field=models.CharField(
                choices=[
                    ("preview", "Readiness preview"),
                    ("skip_mc", "Migration Cloud skip reason"),
                    ("skip_backup", "Box backup skip reason"),
                    ("verify", "Box-side verify snapshot"),
                ],
                db_index=True,
                max_length=16,
            ),
        ),
    ]
