# Default virtual classes to Jitsi (free) instead of Zoom.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("communication", "0012_feed_item_outbound_queue"),
    ]

    operations = [
        migrations.AlterField(
            model_name="virtualclassroom",
            name="provider",
            field=models.CharField(
                choices=[
                    ("ZOOM", "Zoom"),
                    ("GOOGLE_MEET", "Google Meet"),
                    ("JITSI", "Jitsi Meet"),
                    ("TEAMS", "Microsoft Teams"),
                ],
                default="JITSI",
                max_length=20,
            ),
        ),
    ]
