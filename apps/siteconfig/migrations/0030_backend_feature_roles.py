from django.db import migrations, models
import apps.siteconfig.models


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0029_sitesettings_backend_feature_flags"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="backend_feature_flags",
            field=models.JSONField(
                blank=True,
                default=apps.siteconfig.models.default_backend_feature_flags,
                help_text="Backend/front-office admin feature flags (entity console/import, schema UI, bulk limits).",
            ),
        ),
    ]
