# SOT §0.2.1 wedge 14–22: primary sector for RBAC/reporting

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0035_alter_school_sub_system"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="primary_sector",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Primary education system sector (wedge 14–22): PUBLIC, PRIVATE, CHARTER, INTERNATIONAL, FAITH_BASED, HOME_SCHOOL, GOVERNMENT_MINISTRY, NGO, MULTI_CAMPUS.",
                max_length=48,
            ),
        ),
    ]
