"""Wave 3: per-prediction explainability — feature_contributions on RiskFactor."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0023_at_risk_shadow_run_and_comparison"),
    ]

    operations = [
        migrations.AddField(
            model_name="riskfactor",
            name="feature_contributions",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
