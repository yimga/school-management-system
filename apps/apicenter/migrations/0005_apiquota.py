# API Quota model (8.1)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0001_initial"),
        ("apicenter", "0004_apikey"),
    ]

    operations = [
        migrations.CreateModel(
            name="APIQuota",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quota_type", models.CharField(choices=[("requests_per_minute", "Requests per minute"), ("requests_per_day", "Requests per day"), ("webhooks_count", "Webhook subscriptions count")], max_length=32)),
                ("limit_value", models.PositiveIntegerField(help_text="Max allowed (e.g. 100 for requests_per_minute)")),
                ("period_minutes", models.PositiveIntegerField(blank=True, help_text="Optional: period in minutes for rolling window", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="api_quotas",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "ordering": ["quota_type"],
                "verbose_name": "API Quota",
                "verbose_name_plural": "API Quotas",
            },
        ),
        migrations.AddConstraint(
            model_name="apiquota",
            constraint=models.UniqueConstraint(fields=("school", "quota_type"), name="apicenter_apiquota_school_quota_type_uniq"),
        ),
    ]
