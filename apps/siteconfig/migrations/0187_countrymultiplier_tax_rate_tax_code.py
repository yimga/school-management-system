"""v4.00.36 — VAT/regional tax fields on CountryMultiplier.

Closes the audit gap: PPP `multiplier` already existed, but pricing math
ignored local VAT / GST / sales tax. This adds two pure-additive fields
read by ``apps.billing.regional_pricing.compute_localized_price`` at
billing time. No backfill — defaults are correct (0.0000 / "").
"""

from __future__ import annotations

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0186_sitesettings_theme_personality"),
    ]

    operations = [
        migrations.AddField(
            model_name="countrymultiplier",
            name="tax_rate",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0.0000"),
                help_text="VAT / sales-tax rate applied at billing time (e.g. 0.1800 for 18% VAT).",
                max_digits=5,
            ),
        ),
        migrations.AddField(
            model_name="countrymultiplier",
            name="tax_code",
            field=models.CharField(
                blank=True,
                help_text="Local tax code identifier (e.g. VAT, GST, CCAA-IGV); informational only.",
                max_length=32,
            ),
        ),
    ]
