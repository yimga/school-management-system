# Add EdgeOnboardingRun.kind = skip_aspect (operator skip of a per-campus
# infrastructure line: LAN DNS, live sync, roster lab, branding, etc.).
# Choices-only; no schema change besides the documented values.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lifecycle", "0009_edgeonboardingrun_skip_backup_kind"),
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
                    ("skip_aspect", "Infrastructure aspect skip reason"),
                    ("verify", "Box-side verify snapshot"),
                ],
                db_index=True,
                max_length=16,
            ),
        ),
    ]
