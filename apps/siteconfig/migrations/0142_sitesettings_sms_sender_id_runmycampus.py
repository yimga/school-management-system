from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0141_globalsupportticket_assigned_to"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="sms_sender_id",
            field=models.CharField(default="RUNMYCAMPUS", max_length=50),
        ),
    ]
