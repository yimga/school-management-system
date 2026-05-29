"""v4.00.36 — nullable CurrencyRegistry FK on Invoice + Payment.

Additive: keeps the existing ``Payment.currency_code`` CharField and the
implicit ``Invoice.profile.currency_code`` derivation intact. New code
can read ``.currency`` (typed FK row); legacy code keeps working off
the strings. No backfill — null is allowed and sentinel-equivalent.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0065_workforce_offline_capture_1511"),
        ("registries", "0007_tenant_grade_scale_override"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="currency",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Optional canonical currency (registries.CurrencyRegistry). "
                    "When unset, falls back to ComplianceProfile.currency_code on the linked profile."
                ),
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="finance_invoices",
                to="registries.currencyregistry",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="currency",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Optional canonical currency (registries.CurrencyRegistry). "
                    "When unset, falls back to currency_code string."
                ),
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="finance_payments",
                to="registries.currencyregistry",
            ),
        ),
    ]
