# Generated migration to add final_score to Evaluation
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("evals", "0011_alter_evaluationevidence_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="evaluation",
            name="final_score",
            field=models.DecimalField(
                null=True, max_digits=5, decimal_places=2, blank=True
            ),
        ),
    ]
