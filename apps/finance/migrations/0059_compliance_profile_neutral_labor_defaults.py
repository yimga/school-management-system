"""Neutralize ComplianceProfile labor defaults so a fresh row does not silently encode
Cameroon labor law values (previously: min_wage=60000, default_hours_per_week=40,
annual_leave_days=21, maternity_leave_days=84).

New defaults are zero (= 'not configured'); downstream code should treat zero as
'use the country-specific compliance preset', not as a real labor parameter.
Existing rows are untouched.
"""

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0058_payment_gateway_health_snapshot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="complianceprofile",
            name="min_wage",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Statutory minimum wage in this profile's currency. Set per-country at "
                    "onboarding. Zero means 'not configured' and downstream code should treat "
                    "it as unset."
                ),
                max_digits=12,
            ),
        ),
        migrations.AlterField(
            model_name="complianceprofile",
            name="default_hours_per_week",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Standard working hours per week. Set per-country at onboarding "
                    "(e.g. 35 in France, 40 in many other jurisdictions). Zero means 'not configured'."
                ),
                max_digits=6,
            ),
        ),
        migrations.AlterField(
            model_name="complianceprofile",
            name="overtime_multiplier",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("1.5"),
                help_text="Pay multiplier for overtime hours (e.g. 1.5 for time-and-a-half).",
                max_digits=6,
            ),
        ),
        migrations.AlterField(
            model_name="complianceprofile",
            name="annual_leave_days",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text=(
                    "Statutory paid annual leave days. Set per-country at onboarding (varies "
                    "widely; e.g. 10 in the US, 20+ in EU, 21 in Cameroon). Zero means 'not configured'."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="complianceprofile",
            name="maternity_leave_days",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text=(
                    "Statutory paid maternity leave days. Set per-country at onboarding. "
                    "Zero means 'not configured'."
                ),
            ),
        ),
    ]
