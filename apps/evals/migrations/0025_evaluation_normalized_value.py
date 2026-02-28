# Rosetta Stone: normalized grade value for cross-tenant/cross-system reporting

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evals", "0024_enable_rls_postgresql"),
    ]

    operations = [
        migrations.AddField(
            model_name="evaluation",
            name="normalized_value",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Score normalized to 0.0–1.0 for cross-system grade conversion and reporting.",
                max_digits=5,
                null=True,
            ),
        ),
    ]
