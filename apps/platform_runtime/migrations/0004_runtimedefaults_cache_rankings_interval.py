# Generated for Step 4 (ownership move): first-class column for cache_rankings_interval_minutes.
# get_effective_site_settings prefers this over SiteSettings when set; backfill via backfill_runtime_defaults.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0003_backfill_runtimedefaults_from_sitesettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="cache_rankings_interval_minutes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Owned by platform_runtime (Step 4). When set, get_effective_site_settings uses this instead of SiteSettings.",
                null=True,
            ),
        ),
    ]
