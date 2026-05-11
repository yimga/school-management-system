"""Pass offline-foundational closeout: flip RuntimeDefaults.enable_offline_mode
default from null to True so the SW outbox / delta-sync / replay pipeline is live
out of the box. Existing rows are untouched; tenants who explicitly set False or
left null stay as-is.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0062_configuration_change_governance"),
    ]

    operations = [
        migrations.AlterField(
            model_name="runtimedefaults",
            name="enable_offline_mode",
            field=models.BooleanField(
                blank=True,
                default=True,
                help_text=(
                    "Default offline mode toggle. Defaults True (Pass offline-foundational closeout) "
                    "so the SW outbox / delta-sync / replay pipeline is live out of the box; tenants "
                    "with regulatory or bandwidth constraints can flip to False per-school."
                ),
                null=True,
            ),
        ),
    ]
