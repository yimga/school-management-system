# Links API keys and OAuth apps to marketplace lifecycle.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0008_developer_platform_app_catalog"),
        ("apicenter", "0007_developer_platform_oauth"),
    ]

    operations = [
        migrations.AddField(
            model_name="apikey",
            name="marketplace_installation",
            field=models.ForeignKey(
                blank=True,
                help_text="When set, runtime scopes merge key.scopes with tenant scope grants.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="api_keys",
                to="marketplace.appinstallation",
            ),
        ),
        migrations.AddField(
            model_name="developerapplication",
            name="marketplace_app",
            field=models.ForeignKey(
                blank=True,
                help_text="Links OAuth client to a catalog app when applicable.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="developer_applications",
                to="marketplace.marketplaceapp",
            ),
        ),
    ]
