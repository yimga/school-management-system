"""
Switch the 5 hardcoded currency `default="USD"` fields to a settings-driven
callable (`_platform_default_currency`) so new rows pick up
settings.PLATFORM_DEFAULT_CURRENCY at creation time.

Existing rows keep whatever value they already had — this migration just
updates the field-level default. Service code (apps/billing/services.py)
already resolves currency at runtime from tenant region + platform default.

See docs/CONFIGURABILITY.md (Layer B).
"""
from django.conf import settings
from django.db import migrations, models


def _platform_default_currency():
    """Top-level callable for migration safety. Django can serialize a top-level
    function reference but not a lambda. See docs/CONFIGURABILITY.md Layer B.

    Inlined from ``_platform_default_currency`` for
    migration historical-state safety.
    """
    return getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD")


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0006_alter_stripeplanprice_plan_code"),
    ]

    operations = [
        migrations.AlterField(
            model_name="billingaccount",
            name="currency_code",
            field=models.CharField(
                default=_platform_default_currency,
                max_length=3,
            ),
        ),
        migrations.AlterField(
            model_name="platformledgerentry",
            name="currency_code",
            field=models.CharField(
                default=_platform_default_currency,
                max_length=3,
            ),
        ),
        migrations.AlterField(
            model_name="revenuesharepayout",
            name="currency_code",
            field=models.CharField(
                default=_platform_default_currency,
                max_length=3,
            ),
        ),
        migrations.AlterField(
            model_name="stripeplanprice",
            name="currency",
            field=models.CharField(
                default=_platform_default_currency,
                max_length=3,
            ),
        ),
        migrations.AlterField(
            model_name="quote",
            name="currency_code",
            field=models.CharField(
                default=_platform_default_currency,
                max_length=3,
            ),
        ),
    ]
