# Generated manually for BR-08

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("communication", "0016_outbound_queue_retry_idempotency"),
    ]

    operations = [
        migrations.AddField(
            model_name="threadmessage",
            name="locale_target",
            field=models.CharField(
                blank=True,
                default="",
                help_text="BR-08: intended reader locale (e.g. parent UI language) for translation/audit.",
                max_length=10,
            ),
        ),
    ]
