# Schema versioning for domain events (26.2)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0003_webhookdelivery_max_attempts_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="domainevent",
            name="schema_version",
            field=models.CharField(
                default="1.0",
                help_text="Event payload schema version for consumers (26.2).",
                max_length=32,
            ),
        ),
    ]
