from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0011_themepack_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="dashboard_widgets",
            field=models.JSONField(default=list, blank=True),
        ),
    ]
