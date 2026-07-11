# Per-file operator domain tag for the multi-file canonical-CSV upload tagger.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("migration_cloud", "0035_seed_connector_profiles"),
    ]

    operations = [
        migrations.AddField(
            model_name="migrationartifact",
            name="assigned_domain",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text=(
                    "Operator-assigned canonical domain for this file (e.g. 'students', "
                    "'staff', 'finance'). Set from the multi-file upload tagger; OVERRIDES "
                    "inference and accelerator routing so the operator's explicit "
                    "'this file is X' always wins. Blank = auto-detect."
                ),
                max_length=40,
            ),
        ),
    ]
