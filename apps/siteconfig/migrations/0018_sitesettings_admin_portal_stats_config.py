from django.db import migrations, models
import apps.siteconfig.models


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0016_alter_userpreference_timezone"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="admin_portal_stats_config",
            field=models.JSONField(
                blank=True,
                default=apps.siteconfig.models.default_admin_portal_stats_config,
                help_text=(
                    "Admin portal stats JSON. Keys: sections, max_sections, max_items, items. "
                    'Example: {"sections":["academics"],"max_items":2,"items":{"academics":["Students"]}}'
                ),
            ),
        ),
    ]
