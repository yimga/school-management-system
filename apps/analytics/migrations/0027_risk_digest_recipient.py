"""Wave 8: RiskDigestRecipient — operator-configured digest fan-out targets."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0026_grade_prediction_shadow"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RiskDigestRecipient",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("email", "Email"),
                            ("slack_webhook", "Slack incoming webhook"),
                        ],
                        max_length=20,
                    ),
                ),
                ("target", models.CharField(max_length=512)),
                ("label", models.CharField(blank=True, max_length=120)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="risk_digest_recipients",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Risk digest recipient",
                "verbose_name_plural": "Risk digest recipients",
            },
        ),
        migrations.AddConstraint(
            model_name="riskdigestrecipient",
            constraint=models.UniqueConstraint(
                fields=("school", "channel", "target"),
                name="uniq_risk_digest_recipient",
            ),
        ),
        migrations.AddIndex(
            model_name="riskdigestrecipient",
            index=models.Index(
                fields=["school", "enabled"],
                name="analytics_r_school__1c3b8d_idx",
            ),
        ),
    ]
