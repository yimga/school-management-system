"""v4.00.36 Phase 3 — parent/child BillingAccount for multi-campus rollups."""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0010_usage_cap"),
    ]

    operations = [
        migrations.AddField(
            model_name="billingaccount",
            name="parent_account",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "v4.00.36 Phase 3: optional roll-up parent for multi-campus enterprise networks. "
                    "Children retain their own ledger; the parent aggregates via rollup_account_balance()."
                ),
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="child_accounts",
                to="billing.billingaccount",
            ),
        ),
    ]
