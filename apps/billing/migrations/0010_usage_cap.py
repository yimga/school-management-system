"""v4.00.36 Phase 3 — per-tenant usage caps + soft-warn + auto-freeze."""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0009_alter_billingaccount_currency_code_and_more"),
        ("schools", "0038_advancement_donor_gift"),
    ]

    operations = [
        migrations.CreateModel(
            name="UsageCap",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dimension", models.CharField(help_text="Must be one of apps.billing.models_metering.USAGE_DIMENSION_CODES.", max_length=64)),
                ("soft_warn_at", models.PositiveBigIntegerField(default=0, help_text="Emit a soft warning at or above this quantity. 0 = no soft warn.")),
                ("hard_cap", models.PositiveBigIntegerField(default=0, help_text="At or above this quantity, BillingAccount auto-suspends. 0 = no hard cap.")),
                ("period_grain", models.CharField(choices=[("day", "Daily window"), ("month", "Calendar month")], default="day", max_length=16)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="usage_caps", to="schools.school")),
            ],
            options={
                "verbose_name": "Usage cap",
                "verbose_name_plural": "Usage caps",
                "ordering": ["school", "dimension"],
            },
        ),
        migrations.AddConstraint(
            model_name="usagecap",
            constraint=models.UniqueConstraint(fields=("school", "dimension"), name="billing_uniq_usage_cap_school_dimension"),
        ),
    ]
