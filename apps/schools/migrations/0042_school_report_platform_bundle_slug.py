# Per-tenant override for report-platform SKU floor (plan_entitlements depth).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0041_school_impersonation_dual_control"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="report_platform_bundle_slug",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Optional: reports-standard or reports-advanced — overrides platform "
                    "operator default for granular report feature floor when plan/addons/features "
                    "include coarse reports. Empty = use operator default only."
                ),
                max_length=64,
            ),
        ),
    ]
